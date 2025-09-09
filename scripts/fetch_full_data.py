#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_full_data.py
化合物の完全なPubChemデータ取得スクリプト

Usage:
    python scripts/fetch_full_data.py --input data/input/compounds.json --output data/output/full_data
    
Features:
- 化合物ごとの完全なJSONデータを取得
- 個別ファイルとして保存（見本のような1500行のJSONファイル）
- 後続の詳細解析に適した形式
"""

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.processor import CompoundDataProcessor
from src.data.full_data_processor import FullDataProcessor
from config.settings import LOG_FORMAT, LOG_LEVEL


def setup_logging(log_file: str = "fetch_full_data.log"):
    """ログ設定を初期化"""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL),
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("=== PubChem完全データ取得スクリプト開始 ===")
    return logger


def process_full_data(input_path: Path, output_dir: Path) -> None:
    """化合物の完全データを取得して保存"""
    logger = logging.getLogger(__name__)
    
    # 基本データ処理クラス（データ読み込み用）
    basic_processor = CompoundDataProcessor()
    full_processor = FullDataProcessor()
    
    try:
        # データ読み込み
        data = basic_processor.load_json_data(input_path)
        valid_data = basic_processor.validate_and_filter_data(data)
        
        if not valid_data:
            logger.error("有効なデータがありません。処理を終了します。")
            return
        
        logger.info(f"処理対象: {len(valid_data)} 件の化合物")
        
        # 出力ディレクトリ作成
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 完全データ取得・保存
        full_processor.process_compounds_full_data(valid_data, output_dir)
        
        logger.info("処理が正常に完了しました")
        
    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {e}", exc_info=True)
        raise


def cli():
    """コマンドライン インターフェース"""
    parser = argparse.ArgumentParser(
        description="PubChemから化合物の完全データを取得（見本形式の詳細JSONファイル）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    python scripts/fetch_full_data.py --input data/input/compounds.json --output data/output/full_data
    
出力:
    - individual_compounds_YYYYMMDD_HHMMSS/: 各化合物の完全データ（個別JSONファイル）
    - compounds_full_data_summary_YYYYMMDD_HHMMSS.json: 処理概要
    
出力ファイル例:
    - 4436_550-99-2_ナファゾリン塩酸塩.json: 完全なPubChemデータ（約1500行）
    - 6041_61-76-7_フェニレフリン塩酸塩.json: 同上
        """
    )
    
    parser.add_argument(
        "--input", 
        required=True, 
        help="化合物データのJSONファイルパス"
    )
    
    parser.add_argument(
        "--output",
        required=True,
        help="出力ディレクトリパス"
    )
    
    parser.add_argument(
        "--log",
        default="fetch_full_data.log",
        help="ログファイル名 (default: fetch_full_data.log)"
    )
    
    args = parser.parse_args()
    
    # ログ設定
    logger = setup_logging(args.log)
    
    # 入力ファイル検証
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"入力ファイルが存在しません: {input_path}")
        return 1
    
    if not input_path.suffix.lower() == ".json":
        logger.error(f"JSONファイルを指定してください: {input_path}")
        return 1
    
    # 出力ディレクトリ
    output_dir = Path(args.output)
    
    try:
        process_full_data(input_path, output_dir)
        return 0
    except Exception as e:
        logger.error(f"処理失敗: {e}")
        return 1
    finally:
        logger.info("=== PubChem完全データ取得スクリプト終了 ===")


if __name__ == "__main__":
    exit_code = cli()
    sys.exit(exit_code)