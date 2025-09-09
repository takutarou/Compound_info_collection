#!/usr/bin/env python3
"""
物性値抽出スクリプト - PubChemの完全データから化学物性値を抽出

使用方法:
    python3 scripts/extract_properties.py --input data/output/individual_compounds_YYYYMMDD_HHMMSS/
"""
import argparse
import logging
import datetime
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from src.data.property_extractor import PropertyExtractor
from config.settings import OUTPUT_TIMESTAMP_FORMAT


def setup_logging(log_level=logging.INFO):
    """ログ設定"""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # ファイルハンドラ
    log_file = Path('property_extraction.log')
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    
    # コンソールハンドラ
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)
    
    # ルートロガー設定
    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    
    return logger


def main():
    parser = argparse.ArgumentParser(description='PubChem完全データから化学物性値を抽出')
    parser.add_argument('--input', '-i', required=True, 
                       help='個別化合物ファイルが保存されているディレクトリ')
    parser.add_argument('--output', '-o', 
                       help='出力ファイルパス（省略時は自動生成）')
    parser.add_argument('--summary', '-s',
                       help='概要ファイルパス（CIDマッピング用、省略時は自動検索）')
    parser.add_argument('--debug', action='store_true',
                       help='デバッグログを有効化')
    
    args = parser.parse_args()
    
    # ログ設定
    log_level = logging.DEBUG if args.debug else logging.INFO
    logger = setup_logging(log_level)
    
    logger.info("===== 物性値抽出スクリプト開始 =====")
    
    # 入力ディレクトリの確認
    input_dir = Path(args.input)
    if not input_dir.exists():
        logger.error(f"入力ディレクトリが見つかりません: {input_dir}")
        return 1
    
    # 概要ファイルの検索または指定
    if args.summary:
        summary_file = Path(args.summary)
    else:
        # 同じディレクトリ階層で概要ファイルを検索
        parent_dir = input_dir.parent
        summary_files = list(parent_dir.glob('compounds_full_data_summary_*.json'))
        if summary_files:
            summary_file = max(summary_files, key=lambda p: p.stat().st_mtime)  # 最新ファイル
            logger.info(f"概要ファイルを自動検出: {summary_file}")
        else:
            logger.warning("概要ファイルが見つかりません。CID情報なしで処理を続行します。")
            summary_file = Path("dummy.json")  # 存在しないパス
    
    # 出力ファイルパスの設定
    if args.output:
        output_file = Path(args.output)
    else:
        timestamp = datetime.datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
        output_file = Path(f'data/output/extracted_properties_{timestamp}.json')
    
    # 物性値抽出処理
    try:
        extractor = PropertyExtractor()
        
        logger.info(f"入力ディレクトリ: {input_dir}")
        logger.info(f"概要ファイル: {summary_file}")
        logger.info(f"出力ファイル: {output_file}")
        
        # 一括抽出実行
        extracted_data = extractor.batch_extract_properties(input_dir, summary_file)
        
        # 結果の保存
        output_file.parent.mkdir(parents=True, exist_ok=True)
        extractor.save_extracted_properties(extracted_data, output_file)
        
        # 統計情報の表示
        total_compounds = len(extracted_data)
        compounds_with_properties = 0
        total_properties = 0
        
        for cid, data in extracted_data.items():
            # 基本情報以外のプロパティをカウント
            property_keys = ['boiling_point', 'melting_point', 'pka', 'pkb', 
                           'density', 'solubility', 'logp', 'molecular_weight']
            compound_props = sum(1 for key in property_keys if data.get(key, '').strip())
            if compound_props > 0:
                compounds_with_properties += 1
                total_properties += compound_props
        
        logger.info("--- 処理結果サマリー ---")
        logger.info(f"処理した化合物数: {total_compounds}")
        logger.info(f"物性値が見つかった化合物数: {compounds_with_properties}")
        logger.info(f"抽出された物性値総数: {total_properties}")
        logger.info(f"平均物性値数/化合物: {total_properties/total_compounds:.1f}")
        logger.info(f"出力ファイル: {output_file}")
        
        logger.info("===== 物性値抽出スクリプト終了 =====")
        return 0
        
    except Exception as e:
        logger.error(f"処理中にエラーが発生しました: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())