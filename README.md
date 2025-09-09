# Eye Drop Screening - Chemical Compound Information Collection

点眼薬成分のスクリーニングと化学物質情報収集を効率化するPythonプロジェクト

## セットアップ

```bash
# 1. 仮想環境をアクティベート
source eye_drop_env/bin/activate

# 2. 依存関係をインストール（初回のみ）
pip install -r requirements.txt
```

## 実行コマンド一覧

### 1. 基本データ収集（軽量・CSV出力）

```bash
source eye_drop_env/bin/activate
python3 scripts/fetch_compounds_modular.py --input data/input/your_compounds.json
```

### 2. 完全データ収集（詳細・個別JSONファイル）

```bash
source eye_drop_env/bin/activate
python3 -c "
from src.data.full_data_processor import FullDataProcessor
from pathlib import Path
import json

with open('data/input/your_compounds.json', 'r', encoding='utf-8') as f:
    compounds = json.load(f)

processor = FullDataProcessor()
processor.process_compounds_full_data(compounds, Path('data/output'))
"
```

### 3. 物性値抽出（完全データから化学物性値を抽出）

```bash
source eye_drop_env/bin/activate
python3 scripts/extract_properties.py --input data/output/individual_compounds_YYYYMMDD_HHMMSS/
```

### 4. テスト実行（点眼薬成分5化合物での動作確認）

```bash
source eye_drop_env/bin/activate
python3 -c "
from src.data.full_data_processor import FullDataProcessor
from pathlib import Path
import json

with open('data/input/compounds.json', 'r', encoding='utf-8') as f:
    compounds = json.load(f)

processor = FullDataProcessor()
processor.process_compounds_full_data(compounds, Path('data/output'))
"
```

## 実行手順例

### A. 基本的なデータ収集（CSV形式）

```bash
# 1. 仮想環境アクティベート
source eye_drop_env/bin/activate

# 2. 入力ファイルを準備（data/input/compounds.json）
# 3. 基本データ収集実行
python3 scripts/fetch_compounds_modular.py --input data/input/compounds.json

# 4. 結果確認
ls -la data/output/compounds_basic_*.csv
```

### B. 完全データ収集 + 物性値抽出

```bash
# 1. 仮想環境アクティベート  
source eye_drop_env/bin/activate

# 2. 完全データ収集
python3 -c "
from src.data.full_data_processor import FullDataProcessor
from pathlib import Path
import json

with open('data/input/compounds.json', 'r', encoding='utf-8') as f:
    compounds = json.load(f)

processor = FullDataProcessor()
processor.process_compounds_full_data(compounds, Path('data/output'))
"

# 3. 生成されたディレクトリを確認
ls -la data/output/individual_compounds_*/

# 4. 物性値抽出実行（ディレクトリ名を実際のものに置き換え）
python3 scripts/extract_properties.py --input data/output/individual_compounds_20250910_001610/

# 5. 抽出結果確認
ls -la data/output/extracted_properties_*.json
```

### C. デバッグ実行

```bash
# 詳細ログ付きで物性値抽出
source eye_drop_env/bin/activate
python3 scripts/extract_properties.py --input data/output/individual_compounds_YYYYMMDD_HHMMSS/ --debug
```

## 入力ファイル形式

`data/input/compounds.json`に以下の形式で配置：

```json
[
  {
    "inci": "ナファゾリン塩酸塩",
    "function": "eye_drop_ingredient", 
    "cas": "550-99-2"
  },
  {
    "inci": "フェニレフリン塩酸塩",
    "function": "eye_drop_ingredient",
    "cas": "61-76-7"
  }
]
```

## 出力ファイル

### 基本データ収集の出力
- `data/output/compounds_basic_YYYYMMDD_HHMMSS.csv` - CSV形式結果
- `data/output/compounds_basic_YYYYMMDD_HHMMSS.json` - JSON形式結果

### 完全データ収集の出力
- `data/output/individual_compounds_YYYYMMDD_HHMMSS/` - 各化合物の完全データファイル
  - `{CID}_{CAS}_{INCI名}.json` 形式
- `data/output/compounds_full_data_summary_YYYYMMDD_HHMMSS.json` - 処理概要

### 物性値抽出の出力
- `data/output/extracted_properties_YYYYMMDD_HHMMSS.json` - 抽出された物性値
- `property_extraction.log` - 処理ログ

## 主な抽出可能な物性値

- 沸点 (Boiling Point)
- 融点 (Melting Point) 
- pKa/pKb (Dissociation Constants)
- 分子量 (Molecular Weight)
- 密度 (Density)
- 溶解度 (Solubility)
- LogP (分配係数)
- 分子式 (Molecular Formula)
- SMILES構造式