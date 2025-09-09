#!/usr/bin/env python3
"""
Excel to JSON converter for compound data

使用方法:
    python3 scripts/excel_to_json.py --input data/input/target_data.xlsx
"""
import argparse
import json
import pandas as pd
from pathlib import Path
import sys


def convert_excel_to_json(excel_path: str, output_path: str = None) -> str:
    """
    ExcelファイルをJSON形式に変換
    
    Args:
        excel_path: 入力Excelファイルのパス
        output_path: 出力JSONファイルのパス（未指定時は compounds.json）
        
    Returns:
        生成されたJSONファイルのパス
    """
    # Excelファイル読み込み
    df = pd.read_excel(excel_path)
    
    print(f"Excel読み込み完了: {len(df)}行 x {len(df.columns)}列")
    print(f"列名: {list(df.columns)}")
    
    # JSONデータに変換
    compounds = []
    for _, row in df.iterrows():
        compound = {}
        
        # INCI名の設定（複数の列名パターンに対応）
        if '化合物名' in df.columns:
            compound['inci'] = str(row['化合物名']).strip()
        elif 'inci' in df.columns:
            compound['inci'] = str(row['inci']).strip()
        elif 'name' in df.columns:
            compound['inci'] = str(row['name']).strip()
        elif 'compound' in df.columns:
            compound['inci'] = str(row['compound']).strip()
        else:
            compound['inci'] = str(row.iloc[0]).strip()  # 最初の列をINCIとする
            
        # CAS番号の設定（複数の列名パターンに対応）
        if 'CAS' in df.columns:
            compound['cas'] = str(row['CAS']).strip()
        elif 'cas' in df.columns:
            compound['cas'] = str(row['cas']).strip()
        elif 'CAS番号' in df.columns:
            compound['cas'] = str(row['CAS番号']).strip()
        else:
            # CAS番号らしい列を探す
            cas_found = False
            for col in df.columns:
                if 'cas' in col.lower() and not cas_found:
                    compound['cas'] = str(row[col]).strip()
                    cas_found = True
                    break
            if not cas_found:
                compound['cas'] = str(row.iloc[1]).strip() if len(row) > 1 else ""
        
        # 機能の設定
        if 'function' in df.columns:
            compound['function'] = str(row['function']).strip()
        elif '機能' in df.columns:
            compound['function'] = str(row['機能']).strip()
        elif '用途' in df.columns:
            compound['function'] = str(row['用途']).strip()
        else:
            compound['function'] = "eye_drop_ingredient"  # デフォルト値
        
        # 空でない行のみ追加
        if compound['inci'] and compound['cas'] and compound['inci'] != 'nan' and compound['cas'] != 'nan':
            compounds.append(compound)
    
    # 出力パスの決定
    if not output_path:
        output_path = "data/input/compounds.json"
    
    # JSONファイル出力
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(compounds, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 変換完了: {len(compounds)}化合物を {output_file} に保存")
    
    # 変換結果のプレビュー
    print("\n📋 変換結果プレビュー:")
    for i, compound in enumerate(compounds[:3]):
        print(f"  {i+1}. INCI: {compound['inci']}")
        print(f"     CAS: {compound['cas']}")
        print(f"     Function: {compound['function']}")
        print()
    
    if len(compounds) > 3:
        print(f"  ... 他{len(compounds)-3}化合物")
    
    return str(output_file)


def main():
    parser = argparse.ArgumentParser(
        description='ExcelファイルをJSON形式に変換',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
    python3 scripts/excel_to_json.py --input data/input/target_data.xlsx
    python3 scripts/excel_to_json.py --input data/input/my_compounds.xlsx --output data/input/my_compounds.json

対応列名:
    INCI名: 化合物名, inci, name, compound (最初の列)
    CAS番号: CAS, cas, CAS番号 (2番目の列)  
    機能: function, 機能, 用途 (デフォルト: eye_drop_ingredient)
        """
    )
    
    parser.add_argument('--input', '-i', required=True, 
                       help='入力Excelファイルのパス')
    parser.add_argument('--output', '-o', 
                       help='出力JSONファイルのパス（省略時: data/input/compounds.json）')
    
    args = parser.parse_args()
    
    # 入力ファイル確認
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ エラー: ファイルが見つかりません: {input_path}")
        return 1
    
    if not input_path.suffix.lower() in ['.xlsx', '.xls']:
        print(f"❌ エラー: Excelファイルを指定してください: {input_path}")
        return 1
    
    try:
        output_file = convert_excel_to_json(str(input_path), args.output)
        print(f"\n🎉 変換成功! 次のコマンドでデータ収集を開始できます:")
        print(f"python3 scripts/fetch_compounds_modular.py --input {output_file}")
        return 0
        
    except Exception as e:
        print(f"❌ 変換失敗: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())