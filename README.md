# Eye Drop Screening - Chemical Compound Information Collection

点眼薬成分のスクリーニングと化学物質情報収集を効率化するPythonプロジェクト

## 概要

PubChem APIを使用してCAS番号から化学物質の情報を取得し、点眼薬の安全性評価やスクリーニングに活用するためのツールです。

## 主な機能

- CAS番号からPubChem CID/SIDの自動検索
- 化学物質のタイトル、SMILES構造式の取得
- バッチ処理による効率的なデータ処理
- SID対応による検索成功率の向上
- エラーハンドリングとリトライ機能

## プロジェクト構成

```
eye_drop_screening/
├── config/          # 設定ファイル
├── src/            # メインソースコード
│   ├── pubchem/    # PubChem API関連
│   ├── data/       # データ処理関連
│   └── screening/  # 点眼薬スクリーニング関連
├── scripts/        # 実行スクリプト
├── data/           # データファイル
│   ├── input/      # 入力データ
│   ├── output/     # 出力結果
│   └── cache/      # キャッシュ
├── tests/          # テストファイル
└── docs/           # ドキュメント
```

## インストール

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
python scripts/fetch_compounds.py --input data/input/your_compounds.json
```

## 入力ファイル形式

JSONファイルで以下の形式が必要です：

```json
[
  {
    "inci": "化合物名",
    "function": "機能",
    "cas": "123-45-6"
  }
]
```

## 出力

- CSV形式の結果ファイル
- 詳細情報を含むJSONファイル
- 処理ログファイル

## 依存関係

- Python 3.8+
- pandas
- requests
- tqdm
- more-itertools (Python 3.11以前)