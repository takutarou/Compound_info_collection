"""
Data processing and transformation functions
"""
import json
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd
from tqdm import tqdm

from src.pubchem.client import PubChemClient
from src.pubchem.models import CompoundInfo
from config.settings import OUTPUT_TIMESTAMP_FORMAT, SLEEP_CID
import time


class CompoundDataProcessor:
    """化合物データの処理を担当するクラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pubchem_client = PubChemClient()
    
    def load_json_data(self, json_path: Path) -> List[Dict]:
        """JSONファイルから化合物データを読み込み"""
        self.logger.info(f"JSONファイル読み込み: {json_path}")
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.logger.info(f"JSONデータ読み込み完了: {len(data)} 件")
            return data
        except Exception as e:
            self.logger.error(f"JSONファイル読み込み失敗: {e}")
            raise
    
    def validate_and_filter_data(self, data: List[Dict]) -> List[Dict]:
        """有効なCAS番号を持つデータのみフィルタリング"""
        from src.pubchem.utils import validate_cas
        
        valid_data = []
        for item in data:
            cas_number = item.get("cas", "").strip()
            if validate_cas(cas_number):
                valid_data.append(item)
        
        self.logger.info(f"有効なCAS番号を持つデータ: {len(valid_data)} 件 / {len(data)} 件")
        return valid_data
    
    def create_dataframe(self, data: List[Dict]) -> pd.DataFrame:
        """化合物データからDataFrameを作成"""
        df_data = []
        for item in data:
            inci_name = item.get("inci", "").strip()
            function = item.get("function", "").strip()
            cas_number = item.get("cas", "").strip()
            
            df_data.append({
                "function": function,
                "inci_name": inci_name,
                "original_cas": cas_number,
                "CID": pd.NA,
                "SID": pd.NA,
                "Title": pd.NA,
                "CAS": pd.NA,
                "SMILES": pd.NA,
                "IsomericSM": pd.NA,
                "Data_Source": pd.NA  # "CID" or "SID"
            })
        
        df = pd.DataFrame(df_data)
        self.logger.info(f"DataFrame作成完了: {len(df)} 行")
        return df
    
    def search_compounds(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Tuple]]:
        """CAS番号からCID/SID検索を実行"""
        self.logger.info("STEP1: CAS番号からCID/SID検索開始")
        notfound = []
        
        progress_bar = tqdm(df.iterrows(), total=len(df), desc="CID/SID検索")
        
        for idx, row in progress_bar:
            cas_number = row["original_cas"]
            
            search_result = self.pubchem_client.get_cid_from_cas(cas_number)
            
            if search_result.cids:
                # CIDが見つかった場合
                df.at[idx, "CID"] = search_result.cids[0]
                df.at[idx, "Data_Source"] = "CID"
                self.logger.debug(f"行 {idx}: CAS '{cas_number}' → CID {search_result.cids[0]}")
            elif search_result.sids:
                # SIDのみ見つかった場合
                df.at[idx, "SID"] = search_result.sids[0]
                df.at[idx, "Data_Source"] = "SID"
                self.logger.debug(f"行 {idx}: CAS '{cas_number}' → SID {search_result.sids[0]}")
            else:
                # 何も見つからない場合
                notfound.append((idx, row["inci_name"], cas_number))
                self.logger.warning(f"行 {idx}: CAS '{cas_number}' の検索失敗")
                continue
            
            # プログレスバーの説明を更新
            cid_count = df["CID"].notna().sum()
            sid_count = df["SID"].notna().sum()
            progress_bar.set_description(f"検索 (CID: {cid_count}, SID: {sid_count})")
            
            time.sleep(SLEEP_CID)
        
        successful_cids = df["CID"].dropna().astype(int).tolist()
        successful_sids = df["SID"].dropna().astype(int).tolist()
        self.logger.info(f"STEP1完了: CID {len(successful_cids)} 件, SID {len(successful_sids)} 件取得成功")
        
        return df, notfound
    
    def fetch_properties(self, df: pd.DataFrame) -> pd.DataFrame:
        """CIDおよびSIDからプロパティを取得"""
        self.logger.info("STEP2: プロパティ取得開始")
        
        # CIDのプロパティをバッチ取得
        successful_cids = df["CID"].dropna().astype(int).tolist()
        cid_props = self.pubchem_client.fetch_properties_batched(successful_cids)
        
        # SIDのプロパティを個別取得
        successful_sids = df["SID"].dropna().astype(int).tolist()
        sid_props = {}
        if successful_sids:
            self.logger.info(f"SIDプロパティ取得: {len(successful_sids)} 件")
            for sid in tqdm(successful_sids, desc="SIDプロパティ"):
                sid_props[sid] = self.pubchem_client.get_sid_properties(sid)
                time.sleep(SLEEP_CID)
        
        # DataFrameにプロパティを設定
        for idx, row in df.iterrows():
            if pd.notna(row["CID"]):
                # CIDからのプロパティ
                cid = int(row["CID"])
                p = cid_props.get(cid, {})
                df.at[idx, "Title"] = p.get("Title")
                df.at[idx, "SMILES"] = p.get("CanonicalSMILES")
                df.at[idx, "IsomericSM"] = p.get("IsomericSMILES")
            elif pd.notna(row["SID"]):
                # SIDからのプロパティ
                sid = int(row["SID"])
                p = sid_props.get(sid, {})
                df.at[idx, "Title"] = p.get("Title", "SID Record")
                
                # SIDからSMILES情報を取得（利用可能な場合）
                df.at[idx, "SMILES"] = p.get("SMILES", pd.NA)
                df.at[idx, "IsomericSM"] = p.get("IsomericSMILES", pd.NA)
                
                # 関連CIDがある場合は記録
                if "Related_CIDs" in p:
                    self.logger.info(f"SID {sid}: 関連CID {p['Related_CIDs']}")
                
                # SMILES取得状況をログ出力
                smiles_available = pd.notna(df.at[idx, "SMILES"]) or pd.notna(df.at[idx, "IsomericSM"])
                if smiles_available:
                    self.logger.info(f"SID {sid}: SMILES取得成功")
                else:
                    self.logger.debug(f"SID {sid}: SMILES取得不可")
        
        self.logger.info("STEP2完了: プロパティ設定完了")
        return df
    
    def fetch_cas_information(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
        """CIDからCAS情報を取得"""
        self.logger.info("STEP3: CAS 取得開始")
        
        successful_cids = df["CID"].dropna().astype(int).tolist()
        cas_map = self.pubchem_client.fetch_cas_parallel(successful_cids, workers=2)
        
        all_ids = {}
        
        for idx, row in df.iterrows():
            if pd.notna(row["CID"]):
                # CIDの場合：詳細なCAS情報を取得
                cid = int(row["CID"])
                pairs = cas_map.get(cid, [])
                
                if not pairs:
                    # CASが見つからなくても、元のCASを使用
                    df.at[idx, "CAS"] = row["original_cas"]
                    self.logger.info(f"行 {idx}: CID {cid} のCAS情報なし、元のCAS使用")
                else:
                    cid_sel, cas_sel = self.pubchem_client.choose_best_cas({str(cid): pairs}, row["original_cas"])
                    df.at[idx, "CAS"] = cas_sel if cas_sel else row["original_cas"]
                
                # all_ids用のデータ構築（CID）
                all_ids[str(idx)] = {
                    "Function": row["function"],
                    "INCI": row["inci_name"],
                    "Original_CAS": row["original_cas"],
                    "Data_Source": "CID",
                    "CID": cid,
                    "SID": None,
                    "CAS": {
                        "preferred": [c for c, t in pairs if t == "preferred"],
                        "synonym": [c for c, t in pairs if t == "synonym"]
                    },
                    "Title": row["Title"],
                    "SMILES": row["SMILES"],
                    "IsomericSMILES": row["IsomericSM"],
                }
                
            elif pd.notna(row["SID"]):
                # SIDの場合：元のCASのみ使用
                sid = int(row["SID"])
                df.at[idx, "CAS"] = row["original_cas"]
                
                # all_ids用のデータ構築（SID）
                all_ids[str(idx)] = {
                    "Function": row["function"],
                    "INCI": row["inci_name"],
                    "Original_CAS": row["original_cas"],
                    "Data_Source": "SID",
                    "CID": None,
                    "SID": sid,
                    "CAS": {
                        "preferred": [row["original_cas"]],
                        "synonym": []
                    },
                    "Title": row["Title"],
                    "SMILES": row["SMILES"] if pd.notna(row["SMILES"]) else None,
                    "IsomericSMILES": row["IsomericSM"] if pd.notna(row["IsomericSM"]) else None,
                }
        
        self.logger.info("STEP3完了: CAS情報設定完了")
        return df, all_ids
    
    def save_results(self, df: pd.DataFrame, all_ids: Dict, notfound: List[Tuple], json_path: Path) -> None:
        """結果をファイルに保存"""
        timestamp = datetime.datetime.now().strftime(OUTPUT_TIMESTAMP_FORMAT)
        
        # CSV形式で保存
        out_csv = json_path.with_name(f"{json_path.stem}_pubchem_results_{timestamp}.csv")
        out_json = json_path.with_name(f"{json_path.stem}_pubchem_all_ids_{timestamp}.json")
        
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        self.logger.info(f"CSV保存完了: {out_csv.name}")
        
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(all_ids, f, ensure_ascii=False, indent=2)
        self.logger.info(f"JSON保存完了: {out_json.name}")
        
        # 統計情報をログ出力
        self._log_statistics(df, notfound, out_csv, out_json)
        
        # 失敗記録の保存
        if notfound:
            miss_file = json_path.with_name(f"{json_path.stem}_miss_{timestamp}.json")
            with open(miss_file, "w", encoding="utf-8") as f:
                json.dump([{"row": i, "inci_name": n, "cas": c} for i, n, c in notfound], 
                         f, ensure_ascii=False, indent=2)
            self.logger.info(f"失敗記録: {len(notfound)} 行 → {miss_file.name}")
    
    def _log_statistics(self, df: pd.DataFrame, notfound: List[Tuple], out_csv: Path, out_json: Path) -> None:
        """処理結果の統計情報をログ出力"""
        cas_success = df['CAS'].notna().sum()
        cid_success = df['CID'].notna().sum()
        sid_success = df['SID'].notna().sum()
        total_success = cid_success + sid_success
        total_records = len(df)
        
        # SMILES取得状況の統計
        smiles_total = df['SMILES'].notna().sum()
        smiles_from_cid = df[(df['Data_Source'] == 'CID') & df['SMILES'].notna()].shape[0]
        smiles_from_sid = df[(df['Data_Source'] == 'SID') & df['SMILES'].notna()].shape[0]
        
        self.logger.info(f"✅ 処理完了:")
        self.logger.info(f"  CID取得成功: {cid_success}/{total_records} 件")
        self.logger.info(f"  SID取得成功: {sid_success}/{total_records} 件")
        self.logger.info(f"  全体成功率: {total_success}/{total_records} 件 ({total_success/total_records*100:.1f}%)")
        self.logger.info(f"  CAS取得成功: {cas_success}/{total_records} 件")
        self.logger.info(f"  SMILES取得: {smiles_total}/{total_records} 件 (CID: {smiles_from_cid}, SID: {smiles_from_sid})")
        self.logger.info(f"  CSV結果: {out_csv.name}")
        self.logger.info(f"  JSON詳細: {out_json.name}")