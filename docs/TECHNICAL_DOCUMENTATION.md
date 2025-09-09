# Technical Documentation - Eye Drop Screening System

## アーキテクチャ概要

### システム構成

```
eye_drop_screening/
├── config/
│   └── settings.py                   # 設定値管理
├── src/
│   ├── pubchem/
│   │   ├── client.py                # 基本PubChem APIクライアント
│   │   ├── full_data_client.py      # 完全データ取得クライアント  
│   │   ├── models.py                # データモデル
│   │   └── utils.py                 # ユーティリティ関数
│   ├── data/
│   │   ├── processor.py             # 基本データ処理
│   │   ├── full_data_processor.py   # 完全データ処理
│   │   └── property_extractor.py    # 物性値抽出処理
│   └── screening/                   # 将来拡張用
├── scripts/
│   ├── fetch_compounds_modular.py   # 基本データ収集スクリプト
│   ├── fetch_full_data.py           # 完全データ収集スクリプト
│   └── extract_properties.py       # 物性値抽出スクリプト
├── data/
│   ├── input/                       # 入力データファイル
│   ├── output/                      # 出力結果ファイル
│   └── cache/                       # キャッシュファイル
├── reference/                       # サンプル・参考ファイル
├── docs/                           # ドキュメント
└── eye_drop_env/                   # Python仮想環境
```

## モジュール詳細

### config/settings.py

システム全体の設定値を管理する中央設定ファイル。

```python
# API制限対応
SLEEP_CID = 0.2              # API呼び出し間隔（秒）
REQUEST_TIMEOUT = 30         # HTTPリクエストタイムアウト
MAX_RETRIES = 3              # 失敗時の最大リトライ回数

# 出力設定
OUTPUT_TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'  # ファイル名用タイムスタンプ
```

**設計方針**: 環境依存の設定を一箇所に集約し、メンテナンス性を向上。

### src/pubchem/utils.py

共通ユーティリティ関数を提供。

**主要機能**:
- `is_valid_cas(cas_number)`: CAS番号の形式検証（正規表現）
- `safe_get(url, timeout, max_retries)`: エラーハンドリング付きHTTPリクエスト

**技術詳細**:
```python
CAS_PATTERN = re.compile(r'^\d{2,7}-\d{2}-\d$')  # CAS番号の正規表現
```

**リトライロジック**: 指数バックオフによるリトライ機能を内蔵。

### src/pubchem/models.py

データ構造を定義するモデルクラス。

**SearchResult クラス**:
```python
@dataclass
class SearchResult:
    cids: List[int] = field(default_factory=list)
    sids: List[int] = field(default_factory=list) 
    title: str = ""
    smiles: str = ""
    search_success: bool = False
```

**設計方針**: 型安全性とコードの可読性を向上させるためdataclassを採用。

### src/pubchem/client.py

PubChem REST API（基本データ取得）のクライアント実装。

**主要メソッド**:
- `get_cid_from_cas(cas_number)`: CAS→CID/SID変換
- `get_compound_properties(cid)`: CIDから基本プロパティ取得
- `get_cas_information(cid)`: CIDからCAS情報取得

**API エンドポイント**:
```python
# CAS検索
"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/cids/json"

# プロパティ取得
"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/Title,CanonicalSMILES/json"
```

**エラーハンドリング**: HTTPエラー、JSONパースエラー、API制限エラーを適切に処理。

### src/pubchem/full_data_client.py

PubChem View API（完全データ取得）のクライアント実装。

**主要メソッド**:
- `get_full_compound_data(cid)`: CIDから完全なRecord/Section形式データ取得
- `get_full_substance_data(sid)`: SIDから完全データ取得  
- `save_individual_compound_files()`: 個別ファイル保存
- `create_compound_summary()`: 処理結果サマリー作成

**API エンドポイント**:
```python
# 完全データ取得（Record/Section形式）
"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"
```

**データ形式検証**: Record/Section形式の構造を検証し、RecordNumberが一致することを確認。

**再帰的セクション検索**:
```python
def _search_sections_recursive(self, sections, target_heading):
    # PubChemのネストしたSection構造を再帰的に探索
    # 分子式、SMILES、IUPAC名などの特定情報を抽出
```

### src/data/processor.py

基本データ処理のパイプライン実装。

**DataProcessor クラス**:
- 入力JSON → CAS検索 → プロパティ取得 → CSV/JSON出力の完全なワークフロー
- バッチ処理とプログレスバー表示
- 統計情報の自動生成

**処理フロー**:
1. 入力データ検証
2. CAS番号からCID/SID検索（並列処理可能）
3. 基本プロパティ取得
4. 結果の統合とファイル出力

### src/data/full_data_processor.py

完全データ処理のパイプライン実装。

**FullDataProcessor クラス**:
- 大量データ（1,000行以上/化合物）の効率的な処理
- 個別ファイル保存による分散ストレージ
- メモリ効率を考慮した逐次処理

**3ステップ処理**:
1. **STEP1**: CAS → CID/SID検索
2. **STEP2**: 完全データ取得（PubChem View API）
3. **STEP3**: ファイル保存と概要作成

**FullDataAnalyzer クラス**:
- 完全データからの特定プロパティ抽出
- 将来の分析機能拡張のための基盤

### src/data/property_extractor.py

完全データから化学物性値を抽出する専用モジュール。

**PropertyExtractor クラス**:
- PubChemのRecord/Section構造を解析
- Experimental Properties と Computed Properties の両方に対応
- 以下の物性値を抽出:
  - 沸点・融点 (Boiling/Melting Point)
  - pKa/pKb (Dissociation Constants)  
  - 分子量 (Molecular Weight)
  - 密度 (Density)
  - 溶解度 (Solubility)
  - LogP (分配係数)

**主要メソッド**:
- `extract_properties_from_file()`: 単一ファイルから物性値抽出
- `batch_extract_properties()`: ディレクトリ内の全ファイルを一括処理
- `_extract_experimental_properties()`: 実験値の抽出
- `_extract_computed_properties()`: 計算値の抽出

**処理フロー**:
1. JSONファイル読み込み
2. Record/Section階層の探索
3. 目的のTOCHeadingを検索
4. Information配列から値を抽出
5. 単位情報と共に整形して保存

## データフロー

### 基本データ収集フロー

```
Input JSON → CAS Validation → PubChem REST API → Property Extraction → CSV/JSON Output
```

### 完全データ収集フロー  

```
Input JSON → CAS→CID/SID → PubChem View API → Record/Section Processing → Individual Files + Summary
```

### 物性値抽出フロー

```
Individual JSON Files → Record/Section Analysis → Property Search → Value Extraction → Aggregated JSON Output
```

### 統合ワークフロー（推奨）

```
1. Input Preparation (compounds.json)
2. Full Data Collection (FullDataProcessor)
3. Property Extraction (PropertyExtractor)  
4. Analysis & Reporting
```

## API仕様と制限

### PubChem REST API
- **用途**: 基本的な化合物情報（CID、タイトル、SMILES等）
- **制限**: 1秒間に5リクエスト推奨
- **レスポンス**: JSON形式、軽量（< 1KB/化合物）

### PubChem View API  
- **用途**: 完全な化合物データ（Record/Section形式）
- **制限**: 同上
- **レスポンス**: JSON形式、重量（1-100KB/化合物）

## パフォーマンス特性

### 処理速度
- **基本データ**: ~1秒/化合物
- **完全データ**: ~2-3秒/化合物
- **180化合物**: 完全データで10-15分

### メモリ使用量
- **基本データ**: メモリ効率良好（全データをメモリ保持）
- **完全データ**: ストリーミング処理（逐次ファイル書き込み）

### ファイルサイズ
- **基本データ**: 数KB（CSV/JSON）
- **完全データ**: 数MB〜数十MB（個別ファイル群）

## エラーハンドリング戦略

### ネットワークエラー
- 指数バックオフでのリトライ
- タイムアウト設定による無限待機防止

### API エラー
- HTTPステータスコード別の適切な処理
- レート制限時の自動待機

### データエラー
- CAS番号形式の事前検証
- JSON構造の妥当性チェック
- 部分的な失敗の許容（全体処理の継続）

## 拡張性

### 新しいAPI対応
- `src/pubchem/` に新しいクライアントクラスを追加
- 共通インターフェース（`SearchResult`モデル）の再利用

### 新しいデータ処理
- `src/data/` に新しいプロセッサクラスを追加
- パイプライン設計による処理ステップの組み合わせ

### 新しい出力形式
- プロセッサクラスの出力メソッドを拡張
- 設定ファイルでの出力形式選択

## セキュリティ考慮事項

### API キー管理
- 現在は不要（PubChemは公開API）
- 将来の有料API対応時は環境変数での管理

### ファイル入出力
- パストラバーサル攻撃への対策
- ファイル名のサニタイゼーション実装済み

### ネットワーク通信
- HTTPS強制（HTTPからの自動アップグレード）
- SSL証明書検証の有効化

## テストとデバッグ

### ログ設定
```python
import logging
logging.getLogger().setLevel(logging.DEBUG)  # 詳細ログ有効化
```

### デバッグ用設定
```python
# config/settings.py
SLEEP_CID = 0.0  # テスト時はAPI制限を無視
```

### テストデータ
- `reference/` ディレクトリのサンプルファイル使用
- 5化合物での動作確認を推奨

## 実装された機能一覧

### 1. 基本データ収集機能
- **対象**: 軽量な基本プロパティ（CID、タイトル、SMILES等）
- **出力**: CSV/JSON形式
- **スクリプト**: `scripts/fetch_compounds_modular.py`
- **実装クラス**: `DataProcessor`

### 2. 完全データ収集機能  
- **対象**: PubChemの完全なRecord/Section形式データ
- **出力**: 個別JSONファイル（1,000行以上/化合物）
- **スクリプト**: `src.data.full_data_processor.FullDataProcessor`
- **実装クラス**: `FullDataProcessor`, `PubChemFullDataClient`

### 3. 物性値抽出機能
- **対象**: 完全データからの化学物性値抽出
- **出力**: 構造化された物性値JSON
- **スクリプト**: `scripts/extract_properties.py`
- **実装クラス**: `PropertyExtractor`
- **抽出項目**: 沸点、融点、pKa、分子量、密度、溶解度、LogP

### 4. エラーハンドリング・リトライ機能
- HTTPエラーの自動リトライ
- API制限対応（レート制限）
- 部分的失敗の許容（全体処理継続）

### 5. ログ・デバッグ機能
- 詳細なプロセスログ
- プログレスバー表示
- デバッグモード対応
- 統計情報の自動生成

## よくある問題と解決策

### 環境・依存関係の問題

1. **ModuleNotFoundError**
```bash
# 仮想環境を正しくアクティベート
source eye_drop_env/bin/activate
pip install -r requirements.txt
```

2. **仮想環境が見つからない**
```bash
# 仮想環境を新規作成
python3 -m venv eye_drop_env
source eye_drop_env/bin/activate
pip install -r requirements.txt
```

### API・ネットワークの問題

3. **API レート制限エラー**
```python
# config/settings.py で調整
SLEEP_CID = 0.5  # 0.2秒から0.5秒に増加
```

4. **タイムアウトエラー**
```python
# config/settings.py で調整
REQUEST_TIMEOUT = 60  # 30秒から60秒に増加
```

### データ・ファイルの問題

5. **CAS番号検索失敗**
- CAS番号の形式確認（例: 123-45-6）
- 代替名称・IUPAC名での検索を検討
- SID検索の活用

6. **ファイル権限エラー**
```bash
chmod -R 755 data/output/
mkdir -p data/output data/input
```

7. **入力ファイル形式エラー**
```bash
# JSONファイルの構文チェック
python3 -m json.tool data/input/compounds.json
```

### 処理・実行の問題

8. **メモリ不足（大量データ処理時）**
- 完全データ処理では逐次処理を採用済み
- 処理対象を分割して実行

9. **処理の中断・再開**
- 個別ファイル保存により部分的な結果は保持
- 概要ファイルで処理状況を確認可能

10. **物性値抽出で結果が空**
```bash
# デバッグモードで詳細ログ確認
python3 scripts/extract_properties.py --input data/output/individual_compounds_*/ --debug
```

## 将来の改善案

### パフォーマンス向上
- 並列API呼び出し（aiohttp使用）
- キャッシュ機能の実装
- データベース連携

### 機能拡張
- 化学構造の類似性検索
- 物性値の予測機能
- バッチ処理のGUI化

### 運用改善
- ログローテーション
- 設定ファイルの環境別分離
- Docker化対応