import os
import subprocess
import shutil

# 3. Kiểm soát số lượng: 0 = Chạy tất cả, > 0 = Giới hạn số lượng chạy thử
LIMIT = 50

def main():
    base_dir = os.path.abspath(os.path.dirname(__file__))
    benchmark_dir = os.path.join(base_dir, "benchmark")
    
    # 2. Thư mục lưu kết quả tập trung codeflaws/all_results/
    results_dir = os.path.join(base_dir, "codeflaws", "all_results")
    collector_script = os.path.join(base_dir, "data_collector.py")

    os.makedirs(results_dir, exist_ok=True)

    if not os.path.exists(benchmark_dir):
        print(f"Thư mục không tồn tại: {benchmark_dir}")
        return

    # 1. Duyệt thư mục: Tìm tất cả các thư mục con trong benchmark/
    bug_dirs = [d for d in os.listdir(benchmark_dir) if os.path.isdir(os.path.join(benchmark_dir, d))]
    
    # Tính số lượng thực tế sẽ chạy
    total = len(bug_dirs)
    target_count = total if LIMIT <= 0 else min(LIMIT, total)

    print(f"Tổng số bug (thư mục) tìm thấy: {total}. Kế hoạch chạy: {target_count}")

    count = 0
    # 2. Vòng lặp thực thi
    for bug_name in bug_dirs:
        # Áp dụng LIMIT
        if LIMIT > 0 and count >= LIMIT:
            break
            
        bug_path = os.path.join(benchmark_dir, bug_name)
        count += 1
        
        # 4. Hiển thị tiến độ và tên bug đang xử lý
        print(f"[{count}/{target_count}] Đang xử lý Bug: {bug_name}")
        
        # Chạy file data_collector.py bằng thư viện subprocess
        # Quan trọng: Set cwd=bug_path để chạy trong ngữ cảnh của thư mục bug
        try:
            result = subprocess.run(
                ["python3", collector_script],
                cwd=bug_path,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Bạn có thể in ra lỗi nếu cần thiết
            # if result.returncode != 0:
            #     print(f"  -> Script báo lỗi: {result.stderr.strip()}")
                
        except Exception as e:
            print(f"  -> Lỗi hệ thống khi gọi subprocess: {e}")
            continue
            
        # Di chuyển và đổi tên file coverage_data.json
        json_file = os.path.join(bug_path, "coverage_data.json")
        if os.path.exists(json_file):
            dest_file = os.path.join(results_dir, f"{bug_name}.json")
            shutil.move(json_file, dest_file)
        else:
            print(f"  -> CẢNH BÁO: Không sinh ra coverage_data.json cho {bug_name}")

    print("\n[+] ĐÃ KẾT THÚC QUÁ TRÌNH THU THẬP.")
    print(f"[+] Các file JSON được lưu tại: {results_dir}")

if __name__ == "__main__":
    main()
