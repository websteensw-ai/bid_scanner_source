import argparse
from datetime import datetime
from dotenv import load_dotenv
from pipeline import run_pipeline
from exporters.excel_exporter import ExcelExporter

load_dotenv()


def main(days: int, min_score: int, output_file: str):
    evaluated_results = run_pipeline(days=days, min_score=min_score)
    print("\n=== [3/3] 엑셀 리포트 출력 ===")
    ExcelExporter.export(evaluated_results, output_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI/로봇 분야 공공 공고 수집 및 선별 도구")
    parser.add_argument("--days", type=int, default=7, help="조회 기간 (일수, 기본: 7)")
    parser.add_argument("--min-score", type=int, default=70, help="최소 연관도 점수 기준 (기본: 70)")
    parser.add_argument("--output", type=str, default=f"./data/outputs/AI_Notice_Report_{datetime.now().strftime('%Y%m%d')}.xlsx", help="출력 엑셀 경로")

    args = parser.parse_args()
    main(days=args.days, min_score=args.min_score, output_file=args.output)
