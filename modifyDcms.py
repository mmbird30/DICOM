import os
import pydicom
import shutil
import time
from datetime import datetime
from pydicom.multival import MultiValue
from pydicom.uid import generate_uid

# 获取当前时间戳和日期
timestamp = str(int(datetime.now().timestamp()))
current_date = datetime.now().strftime('%Y%m%d')

# 输出目标目录
output_dir_name = "Target"
# 获取脚本所在目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(current_dir, output_dir_name)

# 创建目标目录
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

print(f"脚本位置: {current_dir}")
print(f"输出目录: {output_dir}")

def find_dicom_files(root_directory):
    """递归查找指定目录及其子目录中的所有 DICOM 文件，排除输出目录"""
    all_dicom_files = []

    print(f"开始扫描目录: {root_directory}")
    
    for root, dirs, files in os.walk(root_directory):
        # --- [修复1] 关键修复：防止扫描到输出目录 ---
        # 如果输出目录在当前扫描的路径中，修改 dirs 列表以阻止进入该目录
        if output_dir_name in dirs:
            dirs.remove(output_dir_name)
        
        for file in files:
            # 宽松检查后缀，有些DICOM文件没有后缀，如果需要更严谨可以用 try-read
            if file.lower().endswith(('.dcm', '.dicom', '.ima')):
                full_path = os.path.join(root, file)
                relative_to_dir = os.path.relpath(full_path, root_directory)
                all_dicom_files.append((full_path, relative_to_dir, file))
    
    return all_dicom_files


UID_KEYWORDS_TO_REMAP = {
    'StudyInstanceUID',
    'SeriesInstanceUID',
    'SOPInstanceUID',
    'ReferencedSOPInstanceUID',
}


def get_or_create_uid(uid_map, old_uid):
    """返回旧 UID 对应的新 UID；缺失 UID 则单独生成。"""
    if old_uid is None:
        return generate_uid()

    old_uid = str(old_uid)
    if not old_uid:
        return generate_uid()
    if old_uid not in uid_map:
        uid_map[old_uid] = generate_uid()
    return uid_map[old_uid]


def register_uid_mappings(ds, uid_map):
    """递归收集需要替换的实例级 UID，并为相同旧 UID 保持同一映射。"""
    for element in ds:
        if element.VR == 'SQ':
            for item in element.value:
                register_uid_mappings(item, uid_map)
        elif element.keyword in UID_KEYWORDS_TO_REMAP:
            values = element.value if isinstance(element.value, MultiValue) else [element.value]
            for value in values:
                get_or_create_uid(uid_map, value)


def replace_uid_references(ds, uid_map):
    """递归替换顶层及序列内的 Study、Series、SOP 实例 UID。"""
    for element in ds:
        if element.VR == 'SQ':
            for item in element.value:
                replace_uid_references(item, uid_map)
        elif element.keyword in UID_KEYWORDS_TO_REMAP:
            if isinstance(element.value, MultiValue):
                element.value = [uid_map.get(str(value), value) for value in element.value]
            else:
                element.value = uid_map.get(str(element.value), element.value)

dcm_files_info = find_dicom_files(current_dir)

if not dcm_files_info:
    print("\n指定的目录中没有找到 DICOM 文件")
    exit(1)

print(f"\n总共找到 {len(dcm_files_info)} 个 DICOM 文件")

# --- [修复2] 逻辑修复：建立 Study、Series 和 SOP 层级的 UID 映射 ---
print("\n分析原始 DICOM 文件并建立 UID 映射...")
study_uid_map = {}  # {old_study_uid: new_study_uid}
series_uid_map = {}  # {(old_study_uid, old_series_uid): new_series_uid}
uid_map = {}  # 所有顶层及嵌套实例 UID 的统一映射
files_to_process = []

for full_path, relative_path, filename in dcm_files_info:
    try:
        # --- [修复3] 性能优化：只读取头部信息，不读取像素数据 ---
        ds = pydicom.dcmread(full_path, stop_before_pixels=True)

        original_study_uid = getattr(ds, 'StudyInstanceUID', 'unknown_study')
        original_series_uid = getattr(ds, 'SeriesInstanceUID', 'unknown_series')
        original_sop_uid = getattr(ds, 'SOPInstanceUID', None)

        # 先收集所有顶层和嵌套引用 UID，确保整批文件使用同一映射
        register_uid_mappings(ds, uid_map)
        
        # 如果是新的 Study，生成一个新的 UID
        if original_study_uid not in study_uid_map:
            # --- [修复4] 合规性：使用符合标准的 UID 生成方式 ---
            study_uid_map[original_study_uid] = get_or_create_uid(
                uid_map, original_study_uid
            )

        # 同一个 Study 下的同一个 Series 使用相同的新 UID
        series_key = (original_study_uid, original_series_uid)
        if series_key not in series_uid_map:
            series_uid_map[series_key] = get_or_create_uid(
                uid_map, original_series_uid
            )

        files_to_process.append({
            'full_path': full_path,
            'relative_path': relative_path,
            'new_study_uid': study_uid_map[original_study_uid],
            'new_series_uid': series_uid_map[series_key],
            'new_sop_uid': get_or_create_uid(uid_map, original_sop_uid)
        })

    except Exception as e:
        print(f"警告：无法读取文件 {relative_path}: {e}")

print(f"发现 {len(study_uid_map)} 个不同的 Study (检查)。")
print(f"发现 {len(series_uid_map)} 个不同的 Series (检查)。")
print(f"即将开始处理...\n")

processed_count = 0
for file_info in files_to_process:
    processed_count += 1
    src_path = file_info['full_path']
    rel_path = file_info['relative_path']
    new_study_uid = file_info['new_study_uid']
    new_series_uid = file_info['new_series_uid']
    new_sop_uid = file_info['new_sop_uid']
    
    if processed_count % 10 == 0:
        print(f"进度: {processed_count}/{len(files_to_process)}", end='\r')

    try:
        # 这里需要读取完整数据以保存
        ds = pydicom.dcmread(src_path)

        # 同步替换序列内引用的 Study、Series 和 SOP UID
        replace_uid_references(ds, uid_map)
        
        # 修改 Study、Series 和 SOP 层级的 UID
        ds.StudyInstanceUID = new_study_uid
        ds.SeriesInstanceUID = new_series_uid
        ds.SOPInstanceUID = new_sop_uid

        # 文件元信息中的 SOP UID 必须与数据集中的 SOP UID 保持一致
        if hasattr(ds, 'file_meta') and ds.file_meta is not None:
            ds.file_meta.MediaStorageSOPInstanceUID = new_sop_uid
        
        # 构建输出路径
        dest_path = os.path.join(output_dir, rel_path)
        dest_folder = os.path.dirname(dest_path)
        
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)

        ds.save_as(dest_path)
        
    except Exception as e:
        print(f"\n处理失败: {rel_path} - {e}")

print(f"\n\n所有文件处理完成！")
print(f"共处理: {len(files_to_process)} 个文件")

# 压缩目标文件夹
print("正在压缩文件...")
zip_filename = os.path.join(current_dir, 'modified_dicom_files') # 不需要加 .zip，shutil会自动加
shutil.make_archive(zip_filename, 'zip', output_dir)

print(f'\n压缩包创建成功: {zip_filename}.zip')
