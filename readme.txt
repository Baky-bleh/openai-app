# 📑 フラストレーションレポート・ストリームリットアプリ README  
（openai_app/ 配下に配置してください）

---

## 1. 何ができるアプリか
1. 対話履歴（Slack / Teams など）を貼り付けて  
   ‐ レポート名  
   ‐ レポート種類  
   ‐ フラストレーションレポート（要因の要約）  
   ‐ フラストレーション率  
   の 4 項目を LLM で自動抽出し、画面表示 & `data/records.jsonl` に保存
2. 保存済み JSONL をテーブルで確認し、キーワード検索・並べ替えが可能

---

## 2. フォルダ / ファイル構成

```
openai_app/
├─ data/
│   └─ records.jsonl        # 生成されたレコードを 1 行 1 JSON で永続化
├─ pages/
│   └─ 01_レポート一覧.py   # ② 一覧ページ（Streamlit マルチページ機能）
├─ utils/
│   └─ data_io.py           # JSONL の読み書きユーティリティ
├─ venv/                    # 仮想環境（任意。git 管理外）
├─ .env                     # OPENAI_API_KEY など環境変数を置く
├─ 00_レポート生成.py       # ① レポート生成ページ（起動スクリプト）
└─ requirements.txt         # 必要ライブラリ
```

| ファイル / ディレクトリ | 役割 |
|-------------------------|------|
| `00_レポート生成.py`    | Streamlit エントリ。対話履歴入力 → LLM 呼び出し → 保存 |
| `pages/01_レポート一覧.py` | JSONL を読み込みテーブル表示。キーワード検索・ソート付き |
| `utils/data_io.py`      | ① 改行が欠けても壊れない安全な append<br>② 連結 JSON 救済を含む load |
| `data/records.jsonl`    | 永続データ。無ければ自動生成されます |
| `.env`                  | `OPENAI_API_KEY=sk-...` を書く |
| `requirements.txt`      | pip インストール用依存リスト |

---

## 3. セットアップ手順

```bash
# 1. リポジトリ直下へ
cd openai_app

# 2. (任意) 仮想環境
python -m venv venv
source venv/bin/activate    # Windows: .\venv\Scripts\activate

# 3. 依存ライブラリ
pip install -r requirements.txt

# 4. OpenAI API キー (.env に記載) 例
export OPENAI_API_KEY=s******A
```

---

## 4. 起動と操作

```bash
streamlit run 00_レポート生成.py
```

1. 画面左サイドバー  
   ‐ 📝 レポート生成（初期ページ）  
   ‐ 📊 レポート一覧  
2. 📝 ページ  
   1) 対話履歴を貼り付け → 「🚀 レポート生成」  
   2) 画面にマークダウン整形レポート＆ JSON を確認  
3. 📊 ページ  
   1) テーブルで全レコードを確認  
   2) 上部プルダウンで列ソート  
   3) キーワード入力欄で「レポート名」に含まれる文字列でフィルタ  
   4) 「🔄 最新データを読み込み直す」で即時リロード

---

## 5. JSONL のフォーマット

```
{"レポート名":"営業報告","レポート種類":"週次",
 "フラストレーションレポート":"要求変更が2回発生…",
 "フラストレーション率":"37%","timestamp":"2025-08-03T12:34:56.789Z"}
```

* 1 行 1 JSON  
* 末尾 `\n` 付きで書き込むため git で差分が追いやすい  
* 誤って `}{` と連結されても `load_records()` が分割救済

---