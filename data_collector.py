#!/usr/bin/env python3
import os
import glob
import subprocess
import json
import re
import sys

def get_buggy_file():
    # 1. Thử suy luận tên file buggy từ tên thư mục (cấu trúc thư mục của Codeflaws)
    # VD: 1-A-bug-18353198-18353306 -> file buggy là 1-A-18353198.c
    cwd_name = os.path.basename(os.getcwd())
    parts = cwd_name.split('-')
    if 'bug' in parts:
        try:
            bug_idx = parts.index('bug')
            contest = parts[0]
            problem = parts[1]
            buggy_id = parts[bug_idx+1]
            expected_name = f"{contest}-{problem}-{buggy_id}.c"
            if os.path.exists(expected_name):
                return expected_name
        except IndexError:
            pass

    # 2. Tìm file .c có chữ 'buggy' trong tên (như yêu cầu)
    c_files = glob.glob("*.c")
    for f in c_files:
        if 'buggy' in f.lower():
            return f
            
    # 3. Fallback: Trả về file .c đầu tiên tìm được nếu không khớp các điều kiện trên
    if c_files:
        return c_files[0]
        
    return None

def get_accepted_file():
    # Thử suy luận tên file accepted từ tên thư mục (cấu trúc thư mục của Codeflaws)
    # VD: 1-A-bug-18353198-18353306 -> file accepted là 1-A-18353306.c
    cwd_name = os.path.basename(os.getcwd())
    parts = cwd_name.split('-')
    if 'bug' in parts:
        try:
            bug_idx = parts.index('bug')
            contest = parts[0]
            problem = parts[1]
            accepted_id = parts[bug_idx+2]
            expected_name = f"{contest}-{problem}-{accepted_id}.c"
            if os.path.exists(expected_name):
                return expected_name
        except IndexError:
            pass
    return None

def extract_ground_truth(buggy_file, accepted_file):
    # Dùng lệnh diff để tìm ra các dòng khác nhau, từ đó ánh xạ tới tên hàm nếu có thể
    # nhưng đơn giản nhất là biên dịch cả hai để lấy thông tin AST/function hoặc chạy diff text đơn giản.
    # Trong Codeflaws, tên hàm thay đổi có thể lấy thông qua diff:
    cmd = ["diff", "-u", buggy_file, accepted_file]
    diff_proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    diff_output = diff_proc.stdout

    # Rất thô sơ: Tìm tất cả hàm trong buggy_file
    # Cách tốt hơn: Lọc qua ctags/cscope, nhưng vì chúng ta chỉ cần tên hàm,
    # ta có thể dùng regex đơn giản lấy tên hàm C:
    import re
    func_pattern = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*\s+\**([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{', re.MULTILINE)
    
    with open(buggy_file, 'r') as f:
        buggy_code = f.read()
    
    functions = []
    for match in func_pattern.finditer(buggy_code):
        func_name = match.group(1)
        start_pos = match.start()
        # Tìm dấu ngoặc đóng tương ứng
        open_braces = 0
        end_pos = start_pos
        started = False
        for i in range(start_pos, len(buggy_code)):
            if buggy_code[i] == '{':
                open_braces += 1
                started = True
            elif buggy_code[i] == '}':
                open_braces -= 1
            if started and open_braces == 0:
                end_pos = i
                break
        
        functions.append({
            'name': func_name,
            'start_line': buggy_code.count('\n', 0, start_pos) + 1,
            'end_line': buggy_code.count('\n', 0, end_pos) + 1
        })
    
    # Ánh xạ các dòng bị thay đổi trong diff sang tên hàm
    modified_lines = set()
    for line in diff_output.split('\n'):
        # diff -u header
        if line.startswith('@@'):
            # @@ -start,count +start,count @@
            m = re.search(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', line)
            if m:
                curr_line = int(m.group(1))
        elif line.startswith('-') and not line.startswith('---'):
            modified_lines.add(curr_line)
            curr_line += 1
        elif line.startswith('+') and not line.startswith('+++'):
            pass # code thêm vào không map được với dòng cũ một cách trực tiếp
        elif line.startswith(' '):
            curr_line += 1

    changed_functions = set()
    for func in functions:
        for line in modified_lines:
            if func['start_line'] <= line <= func['end_line']:
                changed_functions.add(func['name'])
                break
                
    # Nếu main() bị sửa đổi và ta không tìm được function nào tốt hơn thì dùng main (nhiều bài CP code tất cả trong main)
    if not changed_functions and len(functions) > 0 and modified_lines:
        changed_functions.add('main')
        
    return list(changed_functions)

def main():
    source_file = get_buggy_file()
    if not source_file:
        print("Lỗi: Không tìm thấy file .c buggy nào trong thư mục hiện tại.", file=sys.stderr)
        sys.exit(1)
        
    print(f"[+] Tìm thấy source file: {source_file}")

    # 1. Biên dịch (Compile) với cờ coverage
    compile_cmd = ["gcc", "-O0", "--coverage", source_file, "-o", "program"]
    print(f"[+] Đang biên dịch: {' '.join(compile_cmd)}")
    try:
        subprocess.run(compile_cmd, check=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Lỗi biên dịch: {e.stderr.decode()}", file=sys.stderr)
        sys.exit(1)

    base_name = os.path.splitext(source_file)[0]
    expected_gcno = f"{base_name}.gcno"
    expected_gcda = f"{base_name}.gcda"

    # Auto-Rename: Quét thẻ .gcno bắt đầu bằng 'program-' đổi tên về <base_name>.gcno
    for file in glob.glob("program-*.gcno") + glob.glob("program.gcno"):
        try:
            os.rename(file, expected_gcno)
        except OSError:
            pass

    # Lấy danh sách input
    inputs = glob.glob("input-*")
    # Lọc bỏ các file heldout-input và chỉ giữ lại input-pos... hoặc input-neg...
    inputs = [i for i in inputs if re.match(r'^input-(pos|neg)\d+$', i)]
    
    results = []
    
    # Hàm hỗ trợ sắp xếp các file input (ví dụ: pos1, pos2, neg1)
    def sort_key(filename):
        m = re.match(r'^input-(pos|neg)(\d+)$', filename)
        if m:
            return (m.group(1), int(m.group(2)))
        return ('', 0)

    # 2 & 3. Chạy test và thu thập coverage
    print(f"[+] Đang thực thi {len(inputs)} test case(s)...")
    for inp in sorted(inputs, key=sort_key):
        m = re.match(r'^input-(pos|neg)(\d+)$', inp)
        test_type = m.group(1)
        tid = m.group(2)
        out_file = f"output-{test_type}{tid}"
        test_id_str = f"{test_type}{tid}"
        
        # Xóa file .gcda cũ của lần chạy trước (nếu có) để tính đúng coverage cho test hiện tại
        if os.path.exists(expected_gcda):
            os.remove(expected_gcda)
            
        # Chạy chương trình với input tương ứng
        out_data = ""
        try:
            with open(inp, 'r') as f_in:
                proc = subprocess.run(["./program"], stdin=f_in, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            out_data = proc.stdout
        except subprocess.TimeoutExpired:
            out_data = "" # Coi như FAIL nếu timeout

        # Auto-Rename: Quét thẻ .gcda bắt đầu bằng 'program-' sau test đổi tên về <base_name>.gcda
        for file in glob.glob("program-*.gcda") + glob.glob("program.gcda"):
            try:
                os.rename(file, expected_gcda)
            except OSError:
                pass
            
        # So sánh kết quả thực tế với output kỳ vọng
        passed = False
        if os.path.exists(out_file):
            with open(out_file, 'r') as f_out:
                expected_data = f_out.read()
            # Normalize khoảng trắng thừa ở cuối (trailing whitespaces) trước khi so sánh
            if out_data.strip() == expected_data.strip():
                passed = True
                
        outcome = "PASS" if passed else "FAIL"
        
        # Chạy `gcov -f` hoặc `llvm-cov gcov -f` để lấy tóm tắt function coverage
        # Thử llvm-cov gcov trước (vì macOS dùng LLVM clang)
        gcov_cmd = ["llvm-cov", "gcov", "-f", source_file]
        try:
            gcov_proc = subprocess.run(gcov_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if gcov_proc.returncode != 0:
                raise subprocess.CalledProcessError(gcov_proc.returncode, gcov_cmd)
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Fallback về gcov thông thường
            gcov_cmd = ["gcov", "-f", source_file]
            gcov_proc = subprocess.run(gcov_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        covered_methods = []
        current_func = None
        
        # Phân tích cú pháp (parse) đầu ra của gcov
        for line in gcov_proc.stdout.splitlines():
            line = line.strip()
            # Ví dụ dòng: Function 'main'
            if line.startswith("Function"):
                m = re.search(r"Function\s+'([^']+)'", line)
                if m:
                    current_func = m.group(1)
            # Ví dụ dòng: Lines executed:100.00% of 10
            elif line.startswith("Lines executed:"):
                if current_func:
                    m = re.search(r"Lines executed:([0-9.]+)%", line)
                    if m:
                        pct = float(m.group(1))
                        if pct > 0.0:
                            covered_methods.append(current_func)
                    current_func = None # Reset
                    
        # Tạm thời append kết quả
        cur_result = {
            "test_id": test_id_str,
            "outcome": outcome,
            "covered_methods": covered_methods
        }
        if not passed:
            cur_result["fail_reason"] = "Output mismatch"
            cur_result["expected_output"] = expected_data.strip() if os.path.exists(out_file) else ""
            cur_result["actual_output"] = out_data.strip()
            
        results.append(cur_result)
        
        print(f"    - Test {test_id_str}: {outcome} (Covered {len(covered_methods)} methods)")
        
    # 4. Xuất mảng kết quả ra file JSON
    
    accepted_file = get_accepted_file()
    ground_truth_funcs = []
    if accepted_file:
        ground_truth_funcs = extract_ground_truth(source_file, accepted_file)
        
    coverage_data = {
        "source_file": source_file,
        "granularity": "method-level",
        "ground_truth_functions": ground_truth_funcs,
        "tests": results
    }
    
    with open("coverage_data.json", "w", encoding="utf-8") as f:
        json.dump(coverage_data, f, indent=2)
    print("\n[+] Đã lưu kết quả tại coverage_data.json")

    # 5. Dọn dẹp (Cleanup) file tạm sinh ra trong quá trình chạy
    for ext in ['.gcda', '.gcno', '.gcov']:
        for f in glob.glob(f"*{ext}"):
            try:
                os.remove(f)
            except OSError:
                pass
    
    # Xoá thêm các file có tiền tố program-* và file program
    for f in glob.glob("program-*"):
        try:
            os.remove(f)
        except OSError:
            pass
            
    if os.path.exists("program"):
        os.remove("program")
    print("[+] Hoàn tất dọn dẹp các file tạm (.gcda, .gcno, .gcov, program). Thư mục đã sạch sẽ.")

if __name__ == "__main__":
    main()
