#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_compounds_modular.py
モジュール化されたPubChem化合物情報取得スクリプト

Usage:
    python scripts/fetch_compounds_modular.py --input data/input/compounds.json
    
Features:
- モジュール化された構成で保守性向上
- CID/SID対応による高い検索成功率
- バッチ処理による効率的なAPI利用
- 詳細なログ出力とエラー処理
"""

import argparse
import logging
import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data.processor import CompoundDataProcessor
from config.settings import LOG_FORMAT, LOG_LEVEL


def setup_logging(log_file: str = "compound_fetch.log"):
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
    logger.info("=== モジュール化PubChem化合物情報取得スクリプト開始 ===")
    return logger


def process_compounds_file(input_path: Path) -> None:
    """化合物情報ファイルを処理"""
    logger = logging.getLogger(__name__)
    processor = CompoundDataProcessor()
    
    try:
        # Step 1: データ読み込みと検証
        data = processor.load_json_data(input_path)
        valid_data = processor.validate_and_filter_data(data)
        
        if not valid_data:
            logger.error("有効なデータがありません。処理を終了します。")
            return
        
        # Step 2: DataFrame作成
        df = processor.create_dataframe(valid_data)
        
        # Step 3: CID/SID検索
        df, notfound = processor.search_compounds(df)
        
        # Step 4: プロパティ取得
        df = processor.fetch_properties(df)
        
        # Step 5: CAS情報取得
        df, all_ids = processor.fetch_cas_information(df)
        
        # Step 6: 結果保存
        processor.save_results(df, all_ids, notfound, input_path)
        
    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {e}", exc_info=True)
        raise


def cli():
    """コマンドライン インターフェース"""
    parser = argparse.ArgumentParser(
        description="CAS番号を持つ化合物JSONファイルからPubChem情報を取得（モジュール化版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
    python scripts/fetch_compounds_modular.py --input data/input/compounds.json
    
入力ファイル形式:
    [
        {
            "inci": "化合物名",
            "function": "機能",
            "cas": "123-45-6"
        }
    ]
        """
    )
    
    parser.add_argument(
        "--input", 
        required=True, 
        help="化合物データのJSONファイルパス"
    )
    
    parser.add_argument(
        "--log",
        default="compound_fetch.log",
        help="ログファイル名 (default: compound_fetch.log)"
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
    
    try:
        process_compounds_file(input_path)
        return 0
    except Exception as e:
        logger.error(f"処理失敗: {e}")
        return 1
    finally:
        logger.info("=== モジュール化PubChem化合物情報取得スクリプト終了 ===")


if __name__ == "__main__":
    exit_code = cli()
    sys.exit(exit_code)