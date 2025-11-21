import os
import shutil
import pydicom
from pathlib import Path

def merge_processed_dicom():
    """
    将处理后的平均PET序列合并到原始DICOM数据集中
    """
    print("=== DICOM数据合并工具 ===")
    
    # 路径配置
    original_dir = r"E:\code\DICOM\13005"  # 原始DICOM目录
    processed_402_dir = r"E:\code\DICOM\13005\processed_series_402"  # 处理后的序列402
    processed_403_dir = r"E:\code\DICOM\13005\processed_series_403"  # 处理后的序列403
    output_dir = r"E:\code\DICOM\13005_merged"  # 最终合并输出目录
    
    print(f"原始DICOM目录: {original_dir}")
    print(f"处理后序列402: {processed_402_dir}")
    print(f"处理后序列403: {processed_403_dir}")
    print(f"输出目录: {output_dir}")
    
    # 检查输入目录
    if not os.path.exists(original_dir):
        print(f"❌ 原始目录不存在: {original_dir}")
        return
    
    if not os.path.exists(processed_402_dir):
        print(f"❌ 处理后序列402目录不存在: {processed_402_dir}")
        return
        
    if not os.path.exists(processed_403_dir):
        print(f"❌ 处理后序列403目录不存在: {processed_403_dir}")
        return
    
    # 创建输出目录
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 1. 分析原始DICOM文件，识别需要排除的序列
    print("\n1. 分析原始DICOM文件...")
    original_files = [f for f in os.listdir(original_dir)]
    print(f"原始文件总数: {len(original_files)}")
    
    series_to_exclude = set()  # 需要排除的序列号
    files_to_copy = []  # 需要复制的文件列表
    excluded_files = []  # 被排除的文件列表
    
    for i, filename in enumerate(original_files):
        if i % 500 == 0:
            print(f"  分析进度: {i}/{len(original_files)}")
        
        try:
            filepath = os.path.join(original_dir, filename)
            ds = pydicom.dcmread(filepath)
            
            series_num = getattr(ds, 'SeriesNumber', None)
            series_desc = getattr(ds, 'SeriesDescription', '')
            modality = getattr(ds, 'Modality', '')
            
            # 检查是否为需要替换的PET序列(402、403)
            is_target_series = (
                series_num in [402, 403] and 
                modality == 'PT'
            )
            
            if is_target_series:
                series_to_exclude.add(series_num)
                excluded_files.append((filename, series_num, series_desc))
            else:
                files_to_copy.append((filename, series_num, series_desc, modality))
                
        except Exception as e:
            print(f"  警告：读取文件失败 {filename}: {e}")
            # 对于无法读取的文件，默认复制
            files_to_copy.append((filename, None, '', ''))
    
    print(f"\n分析完成:")
    print(f"  保留文件: {len(files_to_copy)}")
    print(f"  排除文件: {len(excluded_files)}")
    print(f"  排除的序列号: {sorted(series_to_exclude)}")
    
    # 2. 复制保留的原始文件
    print("\n2. 复制保留的原始文件...")
    for i, (filename, series_num, series_desc, modality) in enumerate(files_to_copy):
        if i % 200 == 0:
            print(f"  复制进度: {i}/{len(files_to_copy)}")
        
        src_path = os.path.join(original_dir, filename)
        dst_path = os.path.join(output_dir, filename)
        
        try:
            shutil.copy2(src_path, dst_path)
        except Exception as e:
            print(f"  复制失败 {filename}: {e}")
    
    # 3. 添加处理后的序列
    print("\n3. 添加处理后的平均序列...")
    
    # 添加序列402的平均文件
    if os.path.exists(processed_402_dir):
        processed_files_402 = [f for f in os.listdir(processed_402_dir) if f.endswith('.dcm')]
        print(f"  序列402平均文件: {len(processed_files_402)}张")
        
        for i, filename in enumerate(processed_files_402):
            src_path = os.path.join(processed_402_dir, filename)
            
            # 生成新的文件名，避免冲突
            new_filename = f"processed_series402_{i+1:03d}.dcm"
            dst_path = os.path.join(output_dir, new_filename)
            
            try:
                shutil.copy2(src_path, dst_path)
            except Exception as e:
                print(f"  复制失败 {filename}: {e}")
    
    # 添加序列403的平均文件
    if os.path.exists(processed_403_dir):
        processed_files_403 = [f for f in os.listdir(processed_403_dir) if f.endswith('.dcm')]
        print(f"  序列403平均文件: {len(processed_files_403)}张")
        
        for i, filename in enumerate(processed_files_403):
            src_path = os.path.join(processed_403_dir, filename)
            
            # 生成新的文件名，避免冲突
            new_filename = f"processed_series403_{i+1:03d}.dcm"
            dst_path = os.path.join(output_dir, new_filename)
            
            try:
                shutil.copy2(src_path, dst_path)
            except Exception as e:
                print(f"  复制失败 {filename}: {e}")
    
    # 4. 验证合并结果
    print("\n4. 验证合并结果...")
    final_files = [f for f in os.listdir(output_dir)]
    print(f"最终文件总数: {len(final_files)}")
    
    # 统计最终序列
    print("\n最终序列统计:")
    final_series_info = {}
    
    for filename in final_files[:100]:  # 只检查前100个文件作为样本
        try:
            filepath = os.path.join(output_dir, filename)
            ds = pydicom.dcmread(filepath)
            
            series_num = getattr(ds, 'SeriesNumber', 'Unknown')
            series_desc = getattr(ds, 'SeriesDescription', 'Unknown')
            modality = getattr(ds, 'Modality', 'Unknown')
            
            if series_num not in final_series_info:
                final_series_info[series_num] = {
                    'description': series_desc,
                    'modality': modality,
                    'count': 0
                }
            final_series_info[series_num]['count'] += 1
            
        except:
            continue
    
    # 显示序列信息（样本）
    for series_num, info in sorted(final_series_info.items(), key=lambda x: str(x[0])):
        marker = ""
        if str(series_num).startswith('10'):  # 新的平均序列
            marker = " ⭐ 新增平均序列"
        elif info['modality'] == 'PT':
            marker = " 🔍 PET序列"
        
        print(f"  序列 {series_num}: {info['count']}张 ({info['modality']}) - {info['description']}{marker}")
    
    print(f"\n✅ 合并完成!")
    print(f"📁 最终数据集: {output_dir}")
    print(f"📊 文件统计:")
    print(f"   原始保留: {len(files_to_copy)} 文件")
    print(f"   新增平均: {len(processed_files_402) + len(processed_files_403)} 文件")
    print(f"   总计: {len(final_files)} 文件")
    
    # 5. 生成详细报告
    print("\n📋 详细替换报告:")
    for filename, series_num, series_desc in excluded_files[:10]:  # 显示前10个被排除的文件
        print(f"  排除: {filename} (序列{series_num}: {series_desc})")
    
    if len(excluded_files) > 10:
        print(f"  ... 还有 {len(excluded_files) - 10} 个文件被排除")
    
    print(f"\n📋 新增文件:")
    print(f"  processed_series402_001.dcm 到 processed_series402_{len(processed_files_402):03d}.dcm")
    print(f"  processed_series403_001.dcm 到 processed_series403_{len(processed_files_403):03d}.dcm")

if __name__ == "__main__":
    merge_processed_dicom()
