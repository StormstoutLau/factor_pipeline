# -*- coding: utf-8 -*-
"""
真实横截面因子数据处理工作流
处理 adminexp_of_gr.pkl 因子数据，应用无前瞻偏差插补
"""

import os
import pickle
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.integrated_data_loader import IntegratedDataLoader
from ..core.lookahead_free_integrated_imputer import LookaheadFreeIntegratedImputer


class RealFactorWorkflow:
    """真实因子数据处理工作流"""

    def __init__(self, factor_path: str, output_dir: str = None):
        self.factor_path = Path(factor_path)
        self.output_dir = Path(output_dir) if output_dir else Path("workflow_output")
        self.output_dir.mkdir(exist_ok=True)

        # 初始化组件
        self.integrated_loader = IntegratedDataLoader()
        self.imputer = None

        # 工作流状态
        self.original_data = None
        self.processed_data = None
        self.imputation_report = None

        print("工作流初始化完成")
        print(f"因子数据路径: {self.factor_path}")
        print(f"输出目录: {self.output_dir}")

    def load_factor_data(self) -> pd.DataFrame:
        """加载因子数据"""
        print("=" * 60)
        print("加载真实因子数据")
        print("=" * 60)

        if not self.factor_path.exists():
            raise FileNotFoundError(f"因子数据文件不存在: {self.factor_path}")

        try:
            # 加载pkl文件
            with open(self.factor_path, "rb") as f:
                data = pickle.load(f)

            print(f"数据类型: {type(data)}")

            # 标准化数据格式
            if isinstance(data, pd.DataFrame):
                self.original_data = self._standardize_dataframe(data)
            elif isinstance(data, dict):
                self.original_data = self._standardize_dict(data)
            else:
                raise ValueError(f"不支持的数据格式: {type(data)}")

            print(f"数据形状: {self.original_data.shape}")
            print(f"时间范围: {self.original_data.index.min()} 到 {self.original_data.index.max()}")
            print(f"资产数量: {len(self.original_data.columns)}")

            # 分析缺失情况
            missing_rate = (
                self.original_data.isnull().sum().sum() / self.original_data.shape[0] / self.original_data.shape[1]
            )
            print(f"整体缺失率: {missing_rate:.4f}")

            # 按资产分析缺失
            asset_missing = self.original_data.isnull().sum()
            print("缺失率最高的5只资产:")
            top_missing = asset_missing.nlargest(5)
            for asset, missing_count in top_missing.items():
                asset_rate = missing_count / len(self.original_data)
                print(f"  {asset}: {asset_rate:.4f}")

            return self.original_data

        except FileNotFoundError:
            raise FileNotFoundError(f"因子数据文件不存在: {self.factor_path}")
        except pickle.UnpicklingError as e:
            raise ValueError(f"数据文件损坏或格式不正确: {e}")
        except Exception as e:
            raise RuntimeError(f"加载因子数据时发生未知错误: {e}") from e

    def _standardize_dataframe(self, data: pd.DataFrame) -> pd.DataFrame:
        """标准化DataFrame格式"""
        print("标准化DataFrame格式...")

        # 确保索引是时间格式
        if not isinstance(data.index, pd.DatetimeIndex):
            if "date" in data.columns:
                data = data.set_index("date")
                data.index = pd.to_datetime(data.index)
            elif "trade_date" in data.columns:
                data = data.set_index("trade_date")
                data.index = pd.to_datetime(data.index)
            else:
                # 尝试将索引转换为时间
                try:
                    data.index = pd.to_datetime(data.index)
                except (ValueError, TypeError):
                    print("警告: 无法将索引转换为时间格式")

        # 按时间排序
        data = data.sort_index()

        # 移除全为NaN的列
        data = data.dropna(axis=1, how="all")

        # 移除全为NaN的行
        data = data.dropna(axis=0, how="all")

        print(f"标准化后形状: {data.shape}")
        return data

    def _standardize_dict(self, data: dict) -> pd.DataFrame:
        """标准化字典格式"""
        print("标准化字典格式...")

        # 假设字典格式为 {date: {asset: value}}
        rows = []
        for date, values in data.items():
            if isinstance(values, dict):
                row = {"date": pd.to_datetime(date)}
                row.update(values)
                rows.append(row)

        df = pd.DataFrame(rows)
        df = df.set_index("date")
        df = df.sort_index()

        return self._standardize_dataframe(df)

    def analyze_data_quality(self) -> dict:
        """分析数据质量"""
        print("\n" + "=" * 60)
        print("数据质量分析")
        print("=" * 60)

        if self.original_data is None:
            raise ValueError("请先加载因子数据")

        quality_report = {
            "basic_info": {
                "shape": self.original_data.shape,
                "time_range": (self.original_data.index.min(), self.original_data.index.max()),
                "assets": list(self.original_data.columns),
            },
            "missing_analysis": self._analyze_missing_patterns(),
            "data_distribution": self._analyze_distribution(),
            "time_series_properties": self._analyze_time_series(),
        }

        # 打印质量报告
        self._print_quality_report(quality_report)

        return quality_report

    def _analyze_missing_patterns(self) -> dict:
        """分析缺失模式"""
        missing_analysis = {}

        # 整体缺失统计
        missing_matrix = self.original_data.isnull()
        missing_analysis["overall_missing_rate"] = missing_matrix.sum().sum() / missing_matrix.size

        # 按时间点的缺失率
        missing_by_time = missing_matrix.mean(axis=1)
        missing_analysis["time_missing_stats"] = {
            "mean": missing_by_time.mean(),
            "std": missing_by_time.std(),
            "max": missing_by_time.max(),
            "min": missing_by_time.min(),
        }

        # 按资产的缺失率
        missing_by_asset = missing_matrix.mean(axis=0)
        missing_analysis["asset_missing_stats"] = {
            "mean": missing_by_asset.mean(),
            "std": missing_by_asset.std(),
            "max": missing_by_asset.max(),
            "min": missing_by_asset.min(),
        }

        # 缺失块分析
        missing_blocks = self._identify_missing_blocks(missing_matrix)
        missing_analysis["missing_blocks"] = missing_blocks

        return missing_analysis

    def _identify_missing_blocks(self, missing_matrix: pd.DataFrame) -> dict:
        """识别缺失块"""
        blocks = []

        for asset in missing_matrix.columns:
            asset_missing = missing_matrix[asset]

            # 找到连续的缺失块
            in_block = False
            start_idx = None

            for i, is_missing in enumerate(asset_missing):
                if is_missing and not in_block:
                    # 开始一个新块
                    in_block = True
                    start_idx = i
                elif not is_missing and in_block:
                    # 结束当前块
                    end_idx = i - 1
                    block_length = end_idx - start_idx + 1

                    if block_length >= 3:  # 只记录长度>=3的块
                        blocks.append(
                            {
                                "asset": asset,
                                "start_date": asset_missing.index[start_idx],
                                "end_date": asset_missing.index[end_idx],
                                "length": block_length,
                            }
                        )

                    in_block = False
                    start_idx = None

            # 处理最后一个块
            if in_block:
                end_idx = len(asset_missing) - 1
                block_length = end_idx - start_idx + 1

                if block_length >= 3:
                    blocks.append(
                        {
                            "asset": asset,
                            "start_date": asset_missing.index[start_idx],
                            "end_date": asset_missing.index[end_idx],
                            "length": block_length,
                        }
                    )

        return {
            "total_blocks": len(blocks),
            "blocks": blocks[:10],  # 只保留前10个块
            "avg_block_length": np.mean([b["length"] for b in blocks]) if blocks else 0,
        }

    def _analyze_distribution(self) -> dict:
        """分析数据分布"""
        distribution_analysis = {}

        # 基本统计量
        valid_data = self.original_data.dropna()
        if not valid_data.empty:
            distribution_analysis["basic_stats"] = {
                "mean": valid_data.mean().mean(),
                "std": valid_data.std().mean(),
                "min": valid_data.min().min(),
                "max": valid_data.max().max(),
                "skewness": valid_data.skew().mean(),
                "kurtosis": valid_data.kurtosis().mean(),
            }

        return distribution_analysis

    def _analyze_time_series(self) -> dict:
        """分析时序特性"""
        ts_analysis = {}

        # 时间序列长度
        ts_analysis["time_series_length"] = len(self.original_data)

        # 时间频率
        if len(self.original_data) > 1:
            time_diffs = self.original_data.index.to_series().diff().dropna()
            ts_analysis["avg_time_interval"] = time_diffs.mean()
            ts_analysis["time_frequency"] = str(time_diffs.mode().iloc[0]) if not time_diffs.empty else "unknown"

        return ts_analysis

    def _print_quality_report(self, report: dict):
        """打印质量报告"""
        print("\n数据质量报告:")
        print("-" * 40)

        # 基本信息
        basic = report["basic_info"]
        print(f"数据形状: {basic['shape']}")
        print(f"时间范围: {basic['time_range'][0]} 到 {basic['time_range'][1]}")
        print(f"资产数量: {len(basic['assets'])}")

        # 缺失分析
        missing = report["missing_analysis"]
        print("\n缺失分析:")
        print(f"  整体缺失率: {missing['overall_missing_rate']:.4f}")
        time_stats = missing['time_missing_stats']
        asset_stats = missing['asset_missing_stats']
        print(
            f"  时间维度缺失率: 均值={time_stats['mean']:.4f}, 最大={time_stats['max']:.4f}"
        )
        print(
            f"  资产维度缺失率: 均值={asset_stats['mean']:.4f}, 最大={asset_stats['max']:.4f}"
        )
        print(f"  缺失块数量: {missing['missing_blocks']['total_blocks']}")

        if missing["missing_blocks"]["blocks"]:
            print("  主要缺失块:")
            for block in missing["missing_blocks"]["blocks"][:3]:
                print(f"    {block['asset']}: {block['start_date']} 到 {block['end_date']} ({block['length']}天)")

    def setup_imputer(self, config: dict = None) -> None:
        """设置插补器"""
        print("\n" + "=" * 60)
        print("设置无前瞻偏差插补器")
        print("=" * 60)

        # 默认配置
        default_config = {"group_by": "sw_industry", "time_aware": True, "validate_compliance": True}

        if config:
            default_config.update(config)

        print("插补器配置:")
        for key, value in default_config.items():
            print(f"  {key}: {value}")

        # 创建插补器
        self.imputer = LookaheadFreeIntegratedImputer(**default_config)

        print("插补器设置完成")

    def run_imputation(self) -> pd.DataFrame:
        """执行插补"""
        print("\n" + "=" * 60)
        print("执行无前瞻偏差插补")
        print("=" * 60)

        if self.original_data is None:
            raise ValueError("请先加载因子数据")

        if self.imputer is None:
            raise ValueError("请先设置插补器")

        try:
            # 执行插补
            print("开始插补处理...")
            self.processed_data = self.imputer.fit_transform(self.original_data)

            # 生成插补报告
            self.imputation_report = self.imputer.get_imputation_report(self.original_data, self.processed_data)

            # 打印插补结果
            self._print_imputation_results()

            return self.processed_data

        except Exception as e:
            print(f"插补执行失败: {e}")
            raise

    def _print_imputation_results(self):
        """打印插补结果"""
        if not self.imputation_report:
            return

        report = self.imputation_report

        print("\n插补结果:")
        print("-" * 40)

        # 基本信息
        info = report["data_info"]
        print(f"原始数据形状: {info['shape']}")
        print(f"原始缺失率: {info['missing_rate']:.4f}")

        # 插补摘要
        summary = report["imputation_summary"]
        print(f"插补后缺失数: {summary['total_imputed']}")
        print(f"插补率: {summary['imputation_rate']:.4f}")
        print(f"添加指示变量数: {summary['indicators_added']}")

        # 合规性结果
        compliance = report["compliance_result"]
        print(f"合规性: {'通过' if compliance['is_compliant'] else '失败'}")
        print(f"违规数量: {len(compliance['violations'])}")
        print(f"合规评分: {compliance['compliance_score']:.4f}")

        # 使用的数据源
        print(f"使用的数据源: {', '.join(report['data_sources_used'])}")

    def save_results(self) -> None:
        """保存处理结果"""
        print("\n" + "=" * 60)
        print("保存处理结果")
        print("=" * 60)

        if self.processed_data is None:
            raise ValueError("没有处理结果可保存")

        # 保存处理后的数据
        output_file = self.output_dir / "processed_factor_data.pkl"
        with open(output_file, "wb") as f:
            pickle.dump(self.processed_data, f)
        print(f"处理后数据已保存: {output_file}")

        # 保存CSV格式（可选）
        csv_file = self.output_dir / "processed_factor_data.csv"
        self.processed_data.to_csv(csv_file)
        print(f"CSV格式已保存: {csv_file}")

        # 保存插补报告
        if self.imputation_report:
            report_file = self.output_dir / "imputation_report.pkl"
            with open(report_file, "wb") as f:
                pickle.dump(self.imputation_report, f)
            print(f"插补报告已保存: {report_file}")

        # 保存工作流摘要
        workflow_summary = {
            "factor_path": str(self.factor_path),
            "output_dir": str(self.output_dir),
            "original_shape": self.original_data.shape,
            "processed_shape": self.processed_data.shape,
            "imputation_config": self.imputer.__dict__ if self.imputer else {},
            "timestamp": datetime.now().isoformat(),
        }

        summary_file = self.output_dir / "workflow_summary.json"
        import json

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(workflow_summary, f, indent=2, ensure_ascii=False, default=str)
        print(f"工作流摘要已保存: {summary_file}")

    def generate_visualization_report(self) -> None:
        """生成可视化报告"""
        print("\n" + "=" * 60)
        print("生成可视化报告")
        print("=" * 60)

        try:
            import matplotlib.pyplot as plt
            import seaborn as sns

            # 设置中文字体
            plt.rcParams["font.sans-serif"] = ["SimHei"]
            plt.rcParams["axes.unicode_minus"] = False

            # 创建图表
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))
            fig.suptitle("因子数据处理报告", fontsize=16)

            # 1. 缺失率热图
            if self.original_data is not None:
                missing_matrix = self.original_data.isnull()
                sns.heatmap(missing_matrix.T, ax=axes[0, 0], cbar=True, cmap="Reds")
                axes[0, 0].set_title("原始数据缺失模式")
                axes[0, 0].set_xlabel("时间")
                axes[0, 0].set_ylabel("资产")

            # 2. 插补前后对比
            if self.processed_data is not None:
                original_missing = self.original_data.isnull().sum().sum()
                processed_missing = self.processed_data.isnull().sum().sum()

                axes[0, 1].bar(["原始数据", "插补后"], [original_missing, processed_missing])
                axes[0, 1].set_title("缺失值数量对比")
                axes[0, 1].set_ylabel("缺失值数量")

            # 3. 数据分布
            if self.processed_data is not None:
                valid_data = self.processed_data.dropna()
                if not valid_data.empty:
                    axes[1, 0].hist(valid_data.values.flatten(), bins=50, alpha=0.7)
                    axes[1, 0].set_title("插补后数据分布")
                    axes[1, 0].set_xlabel("因子值")
                    axes[1, 0].set_ylabel("频次")

            # 4. 时间序列示例
            if self.processed_data is not None:
                sample_assets = self.processed_data.columns[:3]
                for asset in sample_assets:
                    axes[1, 1].plot(self.processed_data.index, self.processed_data[asset], label=asset, alpha=0.7)
                axes[1, 1].set_title("因子值时间序列示例")
                axes[1, 1].set_xlabel("时间")
                axes[1, 1].set_ylabel("因子值")
                axes[1, 1].legend()

            plt.tight_layout()

            # 保存图表
            viz_file = self.output_dir / "visualization_report.png"
            plt.savefig(viz_file, dpi=300, bbox_inches="tight")
            print(f"可视化报告已保存: {viz_file}")

            plt.close()

        except ImportError:
            print("警告: matplotlib或seaborn未安装，跳过可视化报告")
        except Exception as e:
            print(f"生成可视化报告失败: {e}")

    def run_complete_workflow(self, imputer_config: dict = None) -> dict:
        """运行完整工作流"""
        print("开始完整因子数据处理工作流")
        print("=" * 80)

        workflow_results = {"success": False, "steps_completed": [], "errors": []}

        try:
            # 步骤1: 加载数据
            print("\n步骤1: 加载因子数据")
            self.load_factor_data()
            workflow_results["steps_completed"].append("data_loaded")

            # 步骤2: 数据质量分析
            print("\n步骤2: 数据质量分析")
            quality_report = self.analyze_data_quality()
            workflow_results["steps_completed"].append("quality_analyzed")
            workflow_results["quality_report"] = quality_report

            # 步骤3: 设置插补器
            print("\n步骤3: 设置插补器")
            self.setup_imputer(imputer_config)
            workflow_results["steps_completed"].append("imputer_setup")

            # 步骤4: 执行插补
            print("\n步骤4: 执行插补")
            self.run_imputation()
            workflow_results["steps_completed"].append("imputation_completed")

            # 步骤5: 保存结果
            print("\n步骤5: 保存结果")
            self.save_results()
            workflow_results["steps_completed"].append("results_saved")

            # 步骤6: 生成可视化报告
            print("\n步骤6: 生成可视化报告")
            self.generate_visualization_report()
            workflow_results["steps_completed"].append("visualization_generated")

            workflow_results["success"] = True
            print("\n" + "=" * 80)
            print("工作流执行成功!")
            print("=" * 80)

        except Exception as e:
            workflow_results["errors"].append(str(e))
            print(f"\n工作流执行失败: {e}")
            import traceback

            traceback.print_exc()

        return workflow_results


def main():
    """主函数示例"""
    import argparse

    parser = argparse.ArgumentParser(description="真实因子数据处理工作流")
    parser.add_argument("--factor-path", type=str, required=True, help="因子数据文件路径")
    parser.add_argument("--output-dir", type=str, default="workflow_output", help="输出目录")
    parser.add_argument("--group-by", type=str, default="sw_industry", help="分组方式")
    args = parser.parse_args()

    imputer_config = {"group_by": args.group_by, "time_aware": True, "validate_compliance": True}

    workflow = RealFactorWorkflow(args.factor_path, args.output_dir)
    results = workflow.run_complete_workflow(imputer_config)

    print(f"\n工作流完成状态: {'成功' if results['success'] else '失败'}")
    print(f"完成步骤: {', '.join(results['steps_completed'])}")
    if results["errors"]:
        print(f"错误信息: {results['errors']}")


if __name__ == "__main__":
    main()
