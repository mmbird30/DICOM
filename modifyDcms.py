import os
import pydicom
import shutil
import time
from datetime import datetime

# 获取当前时间戳和日期
timestamp = str(int(datetime.now().timestamp()))
current_date = datetime.now().strftime('%Y%m%d')

# 输出目标目录
output_dir = "./Target"

# 创建目标目录
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 只处理脚本所在目录及其子目录中的 DICOM 文件
current_dir = os.path.dirname(os.path.abspath(__file__))

print(f"脚本位置: {current_dir}")
print(f"只处理当前目录及其子目录中的 DICOM 文件")

# 只处理脚本所在的目录
target_directories = [current_dir]

print(f"处理目录: {os.path.basename(current_dir)}")

def find_dicom_files(directories):
    """递归查找指定目录及其子目录中的所有 DICOM 文件"""
    all_dicom_files = []
    
    for directory in directories:
        dir_name = os.path.basename(directory)
        print(f"\n扫描目录: {dir_name}")
        dir_dicom_files = []
        
        # 扫描指定目录及其子目录
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith('.dcm'):
                    full_path = os.path.join(root, file)
                    # 计算相对于扫描目录的相对路径
                    relative_to_dir = os.path.relpath(full_path, directory)
                    
                    dir_dicom_files.append((full_path, relative_to_dir, file))
        
        print(f"  发现 {len(dir_dicom_files)} 个 DICOM 文件")
        all_dicom_files.extend(dir_dicom_files)
    
    return all_dicom_files

dcm_files_info = find_dicom_files(target_directories)

if not dcm_files_info:
    print("\n指定的目录中没有找到 DICOM 文件（.dcm）")
    exit(1)

print(f"\n总共找到 {len(dcm_files_info)} 个 DICOM 文件：")
for full_path, relative_path, filename in dcm_files_info:
    print(f"  {relative_path}")

# 分析原始 DICOM 文件，按照 StudyInstanceUID 和 SeriesInstanceUID 分组
print("\n分析原始 DICOM 文件的序列信息...")
series_groups = {}  # {(original_study_uid, original_series_uid): [file_info_list]}

for full_path, relative_path, filename in dcm_files_info:
    try:
        ds = pydicom.dcmread(full_path)
        original_study_uid = getattr(ds, 'StudyInstanceUID', 'unknown_study')
        original_series_uid = getattr(ds, 'SeriesInstanceUID', 'unknown_series')
        
        key = (original_study_uid, original_series_uid)
        if key not in series_groups:
            series_groups[key] = []
        series_groups[key].append((full_path, relative_path, filename, ds))
        
    except Exception as e:
        print(f"警告：无法读取文件 {relative_path}: {e}")

print(f"发现 {len(series_groups)} 个不同的序列组：")
for i, (key, files) in enumerate(series_groups.items()):
    original_study_uid, original_series_uid = key
    print(f"  序列组 {i+1}: {len(files)} 个文件 (Study: {original_study_uid[:20]}..., Series: {original_series_uid[:20]}...)")

# 为每个序列组生成新的 Study UID 和 Series UID
series_uid_mapping = {}
base_timestamp = str(int(datetime.now().timestamp() * 1000))

for i, (original_key, files) in enumerate(series_groups.items()):
    new_study_uid = f"1.2.840.10008.{base_timestamp}.{i}.study"
    new_series_uid = f"1.2.840.10008.{base_timestamp}.{i}.series"
    
    series_uid_mapping[original_key] = {
        'new_study_uid': new_study_uid,
        'new_series_uid': new_series_uid
    }

# 处理每个 DICOM 文件，保持序列完整性
print(f"\n开始处理 DICOM 文件...")
processed_count = 0

for series_key, files in series_groups.items():
    original_study_uid, original_series_uid = series_key
    uid_info = series_uid_mapping[series_key]
    
    print(f"\n处理序列组: {len(files)} 个文件")
    print(f"  原始 StudyUID: {original_study_uid}")
    print(f"  新的 StudyUID: {uid_info['new_study_uid']}")
    print(f"  新的 SeriesUID: {uid_info['new_series_uid']}")
    
    for file_index, (full_path, relative_path, filename, ds) in enumerate(files):
        processed_count += 1
        print(f"\n  处理文件 ({processed_count}/{len(dcm_files_info)}): {relative_path}")
        
        # 为每个文件生成唯一的 SOPInstanceUID
        sop_timestamp = str(int(datetime.now().timestamp() * 1000000))  # 微秒时间戳
        new_sop_uid = f"1.2.840.10008.{sop_timestamp}.{file_index}.sop"
        
        # 复制原始的 DICOM 数据集
        new_ds = ds.copy()
        
        # 修改 UID 相关字段 - 同一序列使用相同的 Study 和 Series UID
        new_ds.StudyInstanceUID = uid_info['new_study_uid']
        new_ds.SeriesInstanceUID = uid_info['new_series_uid']
        new_ds.SOPInstanceUID = new_sop_uid  # 每个文件都有唯一的 SOP UID
        
        # 创建输出目录结构（保持原始目录结构）
        output_relative_dir = os.path.dirname(relative_path)
        if output_relative_dir:
            output_full_dir = os.path.join(output_dir, output_relative_dir)
            if not os.path.exists(output_full_dir):
                os.makedirs(output_full_dir)
        
        # 设置输出文件路径（保持原始目录结构和文件名）
        output_path = os.path.join(output_dir, relative_path)
        
        # 保存修改后的 DICOM 文件
        try:
            new_ds.save_as(output_path)
            print(f"    已保存: {output_path}")
            print(f"    SOPInstanceUID: {new_sop_uid}")
        except Exception as e:
            print(f"    保存文件失败 {relative_path}: {e}")
        
        # 添加小延迟确保时间戳唯一性
        time.sleep(0.001)

print(f"\n所有文件处理完成！")
print(f"  总共处理: {len(dcm_files_info)} 个 DICOM 文件")
print(f"  序列组数: {len(series_groups)} 个")
print(f"  保持了原始的序列完整性")

# 压缩目标文件夹
folder_path = 'Target'
zip_filename = 'modified_dicom_files.zip'

# 压缩为 ZIP 文件
shutil.make_archive(zip_filename.replace('.zip', ''), 'zip', folder_path)
print(f'\n{zip_filename} 创建成功！')
print(f'包含 {len(series_groups)} 个序列组，共 {len(dcm_files_info)} 个 DICOM 文件。')

