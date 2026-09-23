import os
import pydicom
from collections import defaultdict
import hashlib

# 要分析的目录
data_dir = r"E:\holacare\dcm\08005-V1筛选期--ZDXU"

print("=" * 80)
print("DICOM 文件问题分析工具")
print("=" * 80)
print(f"\n分析目录: {data_dir}\n")

# 存储分析结果
dicom_files = []
uid_records = {
    'StudyInstanceUID': defaultdict(list),
    'SeriesInstanceUID': defaultdict(list),
    'SOPInstanceUID': defaultdict(list)
}
issues = []

def analyze_dicom_file(filepath):
    """详细分析单个DICOM文件"""
    problems = []
    info = {
        'filepath': filepath,
        'filename': os.path.basename(filepath),
        'filesize': os.path.getsize(filepath)
    }
    
    try:
        ds = pydicom.dcmread(filepath, force=True)
        
        # 1. 检查必需的UID
        required_uids = ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']
        for uid_name in required_uids:
            if hasattr(ds, uid_name):
                uid_value = getattr(ds, uid_name)
                info[uid_name] = str(uid_value)
                uid_records[uid_name][str(uid_value)].append(filepath)
            else:
                problems.append(f"缺少必需字段: {uid_name}")
                info[uid_name] = None
        
        # 2. 检查其他重要字段
        important_fields = [
            'PatientID', 'PatientName', 'StudyDate', 'Modality',
            'SOPClassUID', 'TransferSyntaxUID'
        ]
        
        for field in important_fields:
            if hasattr(ds, field):
                info[field] = str(getattr(ds, field))
            else:
                problems.append(f"缺少字段: {field}")
                info[field] = None
        
        # 3. 检查 Transfer Syntax
        if hasattr(ds, 'file_meta') and hasattr(ds.file_meta, 'TransferSyntaxUID'):
            transfer_syntax = str(ds.file_meta.TransferSyntaxUID)
            info['TransferSyntaxUID'] = transfer_syntax
            
            # 检查是否是常见的transfer syntax
            common_syntaxes = [
                '1.2.840.10008.1.2',      # Implicit VR Little Endian
                '1.2.840.10008.1.2.1',    # Explicit VR Little Endian
                '1.2.840.10008.1.2.2',    # Explicit VR Big Endian
                '1.2.840.10008.1.2.4.50', # JPEG Baseline
                '1.2.840.10008.1.2.4.70', # JPEG Lossless
            ]
            if transfer_syntax not in common_syntaxes:
                problems.append(f"不常见的TransferSyntax: {transfer_syntax}")
        
        # 4. 检查字符编码
        if hasattr(ds, 'SpecificCharacterSet'):
            info['SpecificCharacterSet'] = str(ds.SpecificCharacterSet)
        else:
            problems.append("缺少字符编码设置 (SpecificCharacterSet)")
            info['SpecificCharacterSet'] = None
        
        # 5. 检查UID格式
        for uid_name in required_uids:
            if info.get(uid_name):
                uid_value = info[uid_name]
                # UID应该只包含数字和点
                if not all(c.isdigit() or c == '.' for c in uid_value):
                    problems.append(f"{uid_name} 格式异常: {uid_value}")
                # UID长度不应超过64
                if len(uid_value) > 64:
                    problems.append(f"{uid_name} 长度超过64字符: {len(uid_value)}")
                # UID不应以0开头（除了根节点）
                parts = uid_value.split('.')
                for i, part in enumerate(parts):
                    if part.startswith('0') and len(part) > 1:
                        problems.append(f"{uid_name} 包含以0开头的节点: {part}")
        
        # 6. 计算文件MD5（用于检测完全相同的文件）
        with open(filepath, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
            info['md5'] = file_hash
        
        # 7. 检查像素数据
        if hasattr(ds, 'pixel_array'):
            try:
                pixel_array = ds.pixel_array
                info['has_pixel_data'] = True
                info['image_shape'] = str(pixel_array.shape)
            except Exception as e:
                problems.append(f"像素数据读取失败: {str(e)}")
                info['has_pixel_data'] = False
        else:
            info['has_pixel_data'] = False
        
        info['problems'] = problems
        return info
        
    except Exception as e:
        problems.append(f"文件读取失败: {str(e)}")
        info['problems'] = problems
        return info

# 扫描所有DICOM文件
print("正在扫描DICOM文件...\n")
file_count = 0

for root, dirs, files in os.walk(data_dir):
    for file in files:
        if file.lower().endswith(('.dcm', '.dicom')) or not '.' in file:
            filepath = os.path.join(root, file)
            file_count += 1
            print(f"分析文件 {file_count}: {os.path.relpath(filepath, data_dir)}")
            
            file_info = analyze_dicom_file(filepath)
            dicom_files.append(file_info)
            
            if file_info['problems']:
                print(f"  ⚠️  发现 {len(file_info['problems'])} 个问题")

print(f"\n总共扫描了 {len(dicom_files)} 个DICOM文件")

# 生成分析报告
print("\n" + "=" * 80)
print("分析报告")
print("=" * 80)

# 1. UID重复检查
print("\n【1. UID 重复检查】")
print("-" * 80)

uid_duplicates = False
for uid_type in ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']:
    print(f"\n{uid_type}:")
    duplicates = {uid: files for uid, files in uid_records[uid_type].items() if len(files) > 1}
    
    if duplicates:
        uid_duplicates = True
        print(f"  ❌ 发现 {len(duplicates)} 个重复的{uid_type}:")
        for uid, files in duplicates.items():
            print(f"\n    UID: {uid}")
            print(f"    出现次数: {len(files)}")
            for f in files[:5]:  # 只显示前5个
                print(f"      - {os.path.relpath(f, data_dir)}")
            if len(files) > 5:
                print(f"      ... 还有 {len(files) - 5} 个文件")
    else:
        unique_count = len(uid_records[uid_type])
        print(f"  ✓ 没有重复，共 {unique_count} 个唯一{uid_type}")

# 2. 文件完整性检查
print("\n【2. 文件完整性检查】")
print("-" * 80)

files_with_problems = [f for f in dicom_files if f['problems']]
if files_with_problems:
    print(f"❌ 发现 {len(files_with_problems)} 个文件存在问题:\n")
    for file_info in files_with_problems:
        print(f"文件: {os.path.relpath(file_info['filepath'], data_dir)}")
        for problem in file_info['problems']:
            print(f"  - {problem}")
        print()
else:
    print("✓ 所有文件读取正常，没有发现完整性问题")

# 3. 文件MD5重复检查（完全相同的文件）
print("\n【3. 文件内容重复检查 (MD5)】")
print("-" * 80)

md5_map = defaultdict(list)
for file_info in dicom_files:
    if 'md5' in file_info:
        md5_map[file_info['md5']].append(file_info['filepath'])

duplicate_files = {md5: files for md5, files in md5_map.items() if len(files) > 1}
if duplicate_files:
    print(f"❌ 发现 {len(duplicate_files)} 组完全相同的文件:")
    for md5, files in duplicate_files.items():
        print(f"\n  MD5: {md5}")
        for f in files:
            print(f"    - {os.path.relpath(f, data_dir)}")
else:
    print("✓ 没有发现完全相同的文件")

# 4. Transfer Syntax 统计
print("\n【4. Transfer Syntax 统计】")
print("-" * 80)

transfer_syntax_map = defaultdict(int)
for file_info in dicom_files:
    ts = file_info.get('TransferSyntaxUID', 'Unknown')
    transfer_syntax_map[ts] += 1

for ts, count in transfer_syntax_map.items():
    print(f"  {ts}: {count} 个文件")

# 5. 字符编码统计
print("\n【5. 字符编码统计】")
print("-" * 80)

charset_map = defaultdict(int)
for file_info in dicom_files:
    cs = file_info.get('SpecificCharacterSet', 'None')
    charset_map[cs] += 1

for cs, count in charset_map.items():
    print(f"  {cs}: {count} 个文件")

# 6. 详细信息导出
print("\n【6. 生成详细报告】")
print("-" * 80)

report_file = "dicom_analysis_report.txt"
with open(report_file, 'w', encoding='utf-8') as f:
    f.write("DICOM 文件详细分析报告\n")
    f.write("=" * 100 + "\n\n")
    
    for i, file_info in enumerate(dicom_files, 1):
        f.write(f"\n文件 {i}: {file_info['filename']}\n")
        f.write(f"  路径: {file_info['filepath']}\n")
        f.write(f"  大小: {file_info['filesize']} bytes\n")
        f.write(f"  StudyInstanceUID:  {file_info.get('StudyInstanceUID', 'N/A')}\n")
        f.write(f"  SeriesInstanceUID: {file_info.get('SeriesInstanceUID', 'N/A')}\n")
        f.write(f"  SOPInstanceUID:    {file_info.get('SOPInstanceUID', 'N/A')}\n")
        f.write(f"  PatientID:         {file_info.get('PatientID', 'N/A')}\n")
        f.write(f"  Modality:          {file_info.get('Modality', 'N/A')}\n")
        f.write(f"  TransferSyntax:    {file_info.get('TransferSyntaxUID', 'N/A')}\n")
        f.write(f"  字符编码:          {file_info.get('SpecificCharacterSet', 'N/A')}\n")
        f.write(f"  包含像素数据:      {file_info.get('has_pixel_data', 'N/A')}\n")
        f.write(f"  MD5:               {file_info.get('md5', 'N/A')}\n")
        
        if file_info['problems']:
            f.write(f"  ⚠️  问题:\n")
            for problem in file_info['problems']:
                f.write(f"    - {problem}\n")
        
        f.write("-" * 100 + "\n")

print(f"✓ 详细报告已保存到: {report_file}")

# 总结
print("\n" + "=" * 80)
print("总结")
print("=" * 80)

critical_issues = []
if uid_duplicates:
    critical_issues.append("存在 UID 重复")
if files_with_problems:
    critical_issues.append(f"{len(files_with_problems)} 个文件存在完整性问题")
if duplicate_files:
    critical_issues.append(f"{len(duplicate_files)} 组文件内容完全相同")

if critical_issues:
    print("\n❌ 发现以下严重问题:")
    for issue in critical_issues:
        print(f"  - {issue}")
    print("\n这些问题可能导致上传失败！")
else:
    print("\n✓ 未发现明显的问题")
    print("  如果仍然无法上传，请检查:")
    print("  1. 上传系统的具体错误信息")
    print("  2. 系统对Transfer Syntax的要求")
    print("  3. 系统对字符编码的要求")
    print("  4. 网络传输过程中文件是否损坏")

print("\n" + "=" * 80)
