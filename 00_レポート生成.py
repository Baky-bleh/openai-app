import asyncio
import json
import os
import uuid
from datetime import datetime

import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from utils.data_io import append_record

# ---- Agent ライブラリ（社内 / 外部）------------
from agents import Agent, Runner, SQLiteSession

st.set_page_config(page_title="📝 フラストレーションレポート生成", page_icon="📝")

# ------------ デフォルトプロンプト --------------
DEFAULT_AGENT_PROMPT = """
あなたは、チャット履歴からフラストレーションの度合いを分析するアシスタントです。入力されたチャット履歴を基に、以下の形式でレポートを出力してください。

### 出力フォーマット


* **レポート名:** （レポートの名前）
* **レポート種類:** （アドホック、日次、月次、週次など）
* **フラストレーションレポート:** （フラストレーションの原因や状況を簡潔に記述）
* **フラストレーション率:** 〇〇%（範囲ではなく、単一の数値のみを返す）

***

### フラストレーション率の判断基準

チャット内のやり取りに基づき、以下の基準と事例を参考にしてフラストレーション率を判定してください。

#### **フラストレーション率: 0-20% （🟢 スムーズな状態）**

**特徴:** 定型的な報告や確認が中心。軽微な修正依頼はあるものの、やり取りは円滑で、感謝や肯定的な言葉で締めくくられることが多い。

* **定型報告と確認:**
    * `「本日分の更新完了しましたのでご報告いたします。」`
    * `「内容問題ございませんでした！」`
    * `「ご確認いただきありがとうございます。認識相違ございません！」`
* **軽微な修正と迅速な解決:**
    * `「フィルターかかったままとなっている箇所がございましたので、そこだけ修正して納品までご対応お願い致します」` → `「ご確認いただき、ありがとうございます。修正して納品致しました。」`
    * `「本件、メンションについては力石・花田宛てにお願いいたします」` → `「申し訳ございません。本件の報告際のメンションについて承知致しました。」`

***

#### **フラストレーション率: 21-40% （🟡 軽微な問題・非効率の発生）**

**特徴:** プロセス上の軽微なミスや確認不足が発生。謝罪や再確認が増え始めるが、やり取り自体は協力的。

* **プロセス上のミスやフィードバック:**
    * `「昨日のフィードバック内容改めてご確認いただけますと幸いです。アカウントIDの下9桁数字が0になってしまっている...」`
    * `「実は昨日...上記案件管理表へ編集がかけられてしまっていたようでして、復元作業が発生してしまいました...」`
* **不明点の確認や認識のズレ:**
    * `「いただいた内容があまり理解できていないんだけど返せるかしら？」`
    * `「...新しいカテゴリーが追加されたですが、こちらマスターシートに追加してもよろしいでしょうか」`
* **謝罪を伴うやり取り:**
    * `「ご返事遅くなり申し訳ございません。」`
    * `「ご迷惑をおかけしてしまい大変申し訳ございませんでした。今後...控えるよう徹底いたします。」`

***

#### **フラストレーション率: 41-60% （🟠 明確な問題・手戻り）**

**特徴:** 明らかな作業漏れやミスが発生し、具体的な修正指示や手戻りが必要になる。納期の延長依頼や、指示内容の理解不足が見られる。

* **作業漏れやミスに対する指摘:**
    * `「1556行目のPLAY!PLAY!PLAY!もご対応いただけますでしょうか。」`
    * `「『OCEAN』の想定部分なのですが、予算（コスト）だけ下記メディアプランと相違しており…次回ご作成時にご留意いただけますでしょうか？」`
* **指示内容の理解不足と質問:**
    * `「申し訳ございませんが、費用比率1:1で按分する方法を存じておりません。そのため按分方法を教えていただきますと幸いです。」`
    * `「すみません、いただいている質問がよくわからず、どこを確認すればよろしいでしょうか？」`
* **納期の延長依頼:**
    * `「本件のレポートの納期2時間ぐらい延長してもよろしいでしょうか。」`

***

#### **フラストレーション率: 61-80% （🔴 重大な問題・頻発する手戻り）**

**特徴:** 提出物の品質に重大な問題があり、何度も修正のやり取りが発生。指示が複雑化し、コミュニケーションコストが著しく増大している。

* **重大なエラーと緊急の修正依頼:**
    * `「本件レポート集計と管理画面数値があっておらず、確認したところ、集計CPに5月分含め漏れが発生しておりました...早急に...作成をお願いできますでしょうか。」`
    * `「こちらの件ですが数値の反映が壊れていますし、どちらも6月の数値のみが格納されておりExcelが変更されていないです。本件早々に修正をお願いします。」`
* **何度も続く修正と確認のループ:**
    * `「こちらどのファイルのどこを修正したのか教えて頂けますでしょうか？CPVが含まれておらず金額も変わっていないです！」`
    * `「要するに、①5月は誤ったレポート数値を使用＋②6・7月は通常のレポートを使用し、5－7月の通期レポート(PPT)を作成頂きたいというのが今回の依頼になります。」`
* **複雑なルール変更と度重なる質疑:**
    * フロー変更の提案から始まり、MTG設定、参加者調整、認識合わせの質疑応答が長期間にわたって続いている状態。

***

#### **フラストレーション率: 81-100% （🚨 危機的状況・赤字作業）**

**特徴:** **完全に赤字的な作業状態。** 納期遅延が常態化し、同じミスが繰り返し発生。作業品質が著しく低く、能力そのものを問われるような厳しい指摘が入る。コミュニケーションは破綻寸前。

* **深刻な納期遅延と催促:**
    * `「本件につきまして昨日が納期だったんですが、進捗いかがでしょうか？まだ、納品されていないみたいなので可能であれば納期過ぎているのでお早めに作成して納品いただけますと幸いです。」`
* **繰り返される同じミスへの厳しい指摘:**
    * `「Criteoの数値が前回同様こちらと違うみたいです。。。」`→`「やっぱりCriteoの数値が違うみたいでして...」`
    * `「本件コストを転記しているだけなのですが、並走期間ほとんどミスが発生しております。何故でしょうか？明日は更に注意してご対応お願い致します。」`
* **マイクロマネジメント状態の修正依頼:**
    * `「Google・Yahoo!各5件ずつ、最大10個の記載として頂きたいです。」`
    * `「現状キャプチャの画質が荒く競合名の確認が難しいため、次回から...大きく取得いただくことは可能でしょうか？」`
    * 1つのタスクに対して10回以上の具体的な修正指示と確認の往復が発生している。
"""

DEFAULT_JSON_PROMPT = """入力データから次の 4 項目を JSON で抽出してください。
- レポート名
- レポート種類
- フラストレーションレポート(文字列)
- フラストレーション率(テキスト形式の数値)
推論過程は含めず、JSON オブジェクトのみを返してください。
"""

# ------------ OpenAI クライアント --------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


async def run_agent(conversation: str, prompt: str) -> str:
    agent = Agent(name="Frustration Report Agent", instructions=prompt, model = "o3")
    session = SQLiteSession(f"session_{uuid.uuid4()}")
    result = await Runner.run(agent, conversation, session=session)
    return result.final_output


def extract_json(report: str, json_prompt: str) -> dict:
    messages = [
        {"role": "system", "content": json_prompt},
        {"role": "user", "content": report},
    ]
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def clean_html_content(html_content: str) -> str:
    """HTMLコンテンツをプレーンテキストに変換"""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text(separator=' ', strip=True)


def format_teams_conversation(teams_data: dict) -> str:
    """Power AutomateのレスポンスをLLM用の対話履歴にフォーマット"""
    formatted_lines = []
    
    # 依頼内容（最初の投稿）
    request_details = teams_data.get('requestDetails', [])
    if request_details and len(request_details) > 0:
        original_post = request_details[0]
        if original_post and isinstance(original_post, dict) and original_post.get('from'):
            sender_name = original_post.get('from', {}).get('user', {}).get('displayName', '不明なユーザー')
            timestamp = original_post.get('createdDateTime', '')
            subject = original_post.get('subject', '')
            content = clean_html_content(original_post.get('body', {}).get('content', ''))
            
            formatted_lines.append(f"=== 依頼内容 ===")
            formatted_lines.append(f"送信者: {sender_name}")
            formatted_lines.append(f"日時: {timestamp}")
            if subject:
                formatted_lines.append(f"件名: {subject}")
            formatted_lines.append(f"内容: {content}")
            formatted_lines.append("")
    
    # 返信処理 - 実際のデータ構造に合わせて修正
    replies_data = teams_data.get('replies', [])
    if replies_data and len(replies_data) > 0:
        replies_container = replies_data[0]
        if replies_container and isinstance(replies_container, dict):
            replies = replies_container.get('value', [])
            if replies and len(replies) > 0:
                formatted_lines.append("=== 返信・やり取り ===")
                for i, reply in enumerate(replies, 1):
                    if reply and isinstance(reply, dict) and reply.get('from'):
                        sender_name = reply.get('from', {}).get('user', {}).get('displayName', '不明なユーザー')
                        timestamp = reply.get('createdDateTime', '')
                        content = clean_html_content(reply.get('body', {}).get('content', ''))
                        
                        formatted_lines.append(f"返信{i}: {sender_name} ({timestamp})")
                        formatted_lines.append(f"{content}")
                        formatted_lines.append("")
    
    return "\n".join(formatted_lines) if formatted_lines else "データの解析に失敗しました"


def fetch_teams_chat(team_name: str, channel_name: str, subject: str, debug_mode: bool = False) -> tuple[bool, str]:
    """Power Automate flowからTeamsチャットデータを取得"""
    try:
        power_automate_url = 'https://prod-51.japaneast.logic.azure.com:443/workflows/6fd03f1d8b7d43faa34d3ad2f7ea5346/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=tTETGgyiK590LDvsepZC2cmT-6GDvaiEF1Et3FS89fA'
        
        flow_data = {
            'teamName': team_name,
            'channelName': channel_name,
            'subject': subject
        }
        
        response = requests.post(
            power_automate_url,
            json=flow_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code != 200:
            response_text = response.text[:500] if hasattr(response, 'text') else 'No response text'
            return False, f"Power Automateエラー: Status {response.status_code}, Response: {response_text}"
        
        try:
            teams_data = response.json()
        except json.JSONDecodeError as e:
            return False, f"JSON解析エラー: {str(e)}, Response: {response.text[:200]}"
        
        # デバッグ情報をStreamlitに表示
        if debug_mode:
            st.info(f"🔍 デバッグ: 受信データのキー = {list(teams_data.keys()) if isinstance(teams_data, dict) else type(teams_data)}")
            st.code(json.dumps(teams_data, ensure_ascii=False, indent=2), language="json")
        
        formatted_conversation = format_teams_conversation(teams_data)
        
        if not formatted_conversation.strip() or formatted_conversation == "データの解析に失敗しました":
            return False, f"データの解析に失敗しました。デバッグモードを有効にして詳細を確認してください。"
        
        return True, formatted_conversation
        
    except requests.exceptions.Timeout:
        return False, "リクエストがタイムアウトしました (30秒)"
    except requests.exceptions.RequestException as e:
        return False, f"ネットワークエラー: {str(e)}"
    except AttributeError as e:
        return False, f"データ属性エラー (NoneType): {str(e)}"
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return False, f"予期せぬエラー: {str(e)}\n詳細: {error_details[:200]}..."


# ================= Streamlit UI =================
st.header("📝 フラストレーションレポート生成")

with st.expander("システムプロンプトを編集する", expanded=False):
    agent_prompt = st.text_area("Agent Prompt", value=DEFAULT_AGENT_PROMPT, height=180)

with st.expander("JSON 抽出プロンプトを編集する", expanded=False):
    json_prompt = st.text_area("JSON Prompt", value=DEFAULT_JSON_PROMPT, height=120)

# Teams チャット取得セクション
with st.expander("📥 Teamsから履歴を取得", expanded=False):
    st.write("チーム内の対話履歴を自動取得してフラストレーション分析を行えます。")
    
    col1, col2 = st.columns(2)
    with col1:
        team_name = st.text_input("チーム名", placeholder="例: プロジェクトチーム")
        subject = st.text_input("メッセージのキーワード（件名）", placeholder="例: 週次報告")
    
    with col2:
        channel_name = st.text_input("チャンネル名", placeholder="例: 全般")
    
    if st.button("📥 Teamsから履歴を取得", disabled=not (team_name and channel_name and subject)):
        with st.spinner("Teamsから履歴を取得中..."):
            success, result = fetch_teams_chat(team_name, channel_name, subject, False)
            
        if success:
            st.success("✅ 履歴を取得しました！下記の対話履歴欄に自動入力されます。")
            st.session_state.conversation_content = result
        else:
            st.error(f"❌ エラー: {result}")

# 対話履歴入力欄（Teams取得データまたは手動入力）
conversation = st.text_area(
    "対話履歴を貼り付けてください", 
    value=st.session_state.get('conversation_content', ''),
    height=280,
    help="手動で貼り付けるか、上の「Teamsから履歴を取得」ボタンを使用してください"
)

if st.button("🚀 レポート生成", disabled=not conversation.strip()):
    with st.spinner("LLM 生成中..."):
        report = asyncio.run(run_agent(conversation, agent_prompt))
        extracted = extract_json(report, json_prompt)
        extracted["timestamp"] = datetime.now().isoformat()
        append_record(extracted)

    st.success("✅ 生成＆保存しました")
    st.subheader("出力レポート")
    st.code(report, language="markdown")
    st.subheader("保存された JSON")
    st.json(extracted, expanded=False)