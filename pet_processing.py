import os
import pydicom
import numpy as np
from pathlib import Path
from collections import defaultdict

def analyze_multiphase_series(input_dir):
    """
    分析DICOM目录，识别多时相序列
    通过检测相同切片位置的重复图像数量来判断时相数
    """
    print("=== DICOM 多时相序列分析工具 ===\n")
    
    # 检查目录
    if not os.path.exists(input_dir):
        print(f"❌ 目录不存在: {input_dir}")
        return None, []
    
    print(f"📁 分析目录: {input_dir}")
    all_files = [f for f in os.listdir(input_dir)]
    print(f"📊 文件总数: {len(all_files)}\n")
    
    if len(all_files) == 0:
        print("❌ 目录为空!")
        return None, []
    
    # 收集序列信息
    print("🔍 扫描文件...")
    series_data = defaultdict(lambda: {
        'description': '',
        'modality': '',
        'files': [],
        'slice_positions': defaultdict(list),  # 记录每个切片位置的实例
        'instance_numbers': []
    })
    
    failed_count = 0
    for i, filename in enumerate(all_files):
        if (i + 1) % 500 == 0:
            print(f"  进度: {i + 1}/{len(all_files)}")
        
        try:
            filepath = os.path.join(input_dir, filename)
            ds = pydicom.dcmread(filepath, stop_before_pixels=True)  # 不读取像素数据，加速
            
            series_num = getattr(ds, 'SeriesNumber', None)
            series_desc = getattr(ds, 'SeriesDescription', 'Unknown')
            modality = getattr(ds, 'Modality', 'Unknown')
            instance_num = getattr(ds, 'InstanceNumber', None)
            
            # 获取切片位置
            slice_location = getattr(ds, 'SliceLocation', None)
            image_position = getattr(ds, 'ImagePositionPatient', None)
            
            # 使用 Z 坐标作为切片位置标识
            if image_position and len(image_position) >= 3:
                z_pos = round(float(image_position[2]), 2)  # 保留2位小数
            elif slice_location is not None:
                z_pos = round(float(slice_location), 2)
            else:
                z_pos = None
            
            if series_num is not None:
                series_data[series_num]['description'] = series_desc
                series_data[series_num]['modality'] = modality
                series_data[series_num]['files'].append(filename)
                series_data[series_num]['instance_numbers'].append(instance_num)
                
                if z_pos is not None:
                    series_data[series_num]['slice_positions'][z_pos].append({
                        'instance': instance_num,
                        'filename': filename
                    })
        
        except Exception as e:
            failed_count += 1
            if failed_count <= 5:
                print(f"  ⚠️  读取失败: {filename} - {e}")
    
    print(f"✅ 扫描完成\n")
    
    if failed_count > 0:
        print(f"⚠️  共 {failed_count} 个文件读取失败\n")
    
    # 分析每个序列
    print("=" * 80)
    print("📋 序列分析报告")
    print("=" * 80)
    
    multiphase_series = []
    
    for series_num in sorted(series_data.keys()):
        info = series_data[series_num]
        total_images = len(info['files'])
        unique_slices = len(info['slice_positions'])
        
        # 计算时相数（每个切片位置的平均图像数）
        if unique_slices > 0:
            phases_per_slice = []
            for z_pos, instances in info['slice_positions'].items():
                phases_per_slice.append(len(instances))
            
            avg_phases = np.mean(phases_per_slice) if phases_per_slice else 0
            max_phases = max(phases_per_slice) if phases_per_slice else 0
            min_phases = min(phases_per_slice) if phases_per_slice else 0
            
            # 判断是否为多时相
            is_multiphase = max_phases > 1
        else:
            avg_phases = 0
            max_phases = 0
            min_phases = 0
            is_multiphase = False
        
        # 显示序列信息
        marker = ""
        if is_multiphase:
            marker = " 🔴 [多时相]"
            multiphase_series.append(series_num)
        
        print(f"\n【序列 {series_num}】{marker}")
        print(f"  描述: {info['description']}")
        print(f"  模态: {info['modality']}")
        print(f"  总图像数: {total_images}")
        print(f"  唯一切片数: {unique_slices}")
        
        if unique_slices > 0:
            print(f"  每切片时相数:")
            print(f"    - 平均: {avg_phases:.1f}")
            print(f"    - 最大: {max_phases}")
            print(f"    - 最小: {min_phases}")
            
            if is_multiphase:
                print(f"  ✅ 检测到多时相序列（约{int(avg_phases)}期动态扫描）")
                
                # 显示一些切片样本
                sample_slices = list(info['slice_positions'].items())[:3]
                print(f"  切片样本:")
                for z_pos, instances in sample_slices:
                    inst_nums = [inst['instance'] for inst in instances[:5]]
                    print(f"    Z={z_pos}: {len(instances)}个时相 - 实例号 {inst_nums}")
    
    # 总结
    print("\n" + "=" * 80)
    print("📊 分析总结")
    print("=" * 80)
    print(f"总序列数: {len(series_data)}")
    print(f"多时相序列数: {len(multiphase_series)}")
    
    if multiphase_series:
        print(f"\n🔴 多时相序列列表: {multiphase_series}")
        print("\n建议处理这些序列以进行时相平均")
    else:
        print("\n✅ 未检测到多时相序列")
    
    return series_data, multiphase_series

def debug_pet_processing():
    """
    调试版本：详细显示扫描过程
    """
    print("=== 调试模式：PET处理 ===")
    
    input_dir = r"E:\code\DICOM\download_1757384807"
    
    # 检查目录是否存在
    if not os.path.exists(input_dir):
        print(f"❌ 目录不存在: {input_dir}")
        return
    
    # 1. 详细扫描
    print(f"\n1. 扫描目录: {input_dir}")
    all_files = [f for f in os.listdir(input_dir)]  # 移除.dcm扩展名限制
    print(f"找到 {len(all_files)} 个文件")
    
    if len(all_files) == 0:
        print("❌ 未找到任何文件!")
        return
    
    # 显示前几个文件名
    print("文件样例:")
    for i, filename in enumerate(all_files[:5]):
        print(f"  {filename}")
    
    # 2. 逐个分析文件
    print(f"\n2. 分析DICOM文件...")
    series_info = {}
    failed_count = 0
    
    for i, filename in enumerate(all_files):
        if i % 200 == 0:
            print(f"  已分析 {i}/{len(all_files)}")
        
        try:
            filepath = os.path.join(input_dir, filename)
            ds = pydicom.dcmread(filepath)
            
            series_num = getattr(ds, 'SeriesNumber', 'Unknown')
            series_desc = getattr(ds, 'SeriesDescription', 'Unknown')
            modality = getattr(ds, 'Modality', 'Unknown')
            instance_num = getattr(ds, 'InstanceNumber', 0)
            
            # 记录信息
            if series_num not in series_info:
                series_info[series_num] = {
                    'count': 0,
                    'description': series_desc,
                    'modality': modality,
                    'files': []
                }
            
            series_info[series_num]['count'] += 1
            series_info[series_num]['files'].append({
                'path': filepath,
                'instance': instance_num,
                'filename': filename
            })
            
        except Exception as e:
            failed_count += 1
            if failed_count <= 3:  # 只显示前3个错误
                print(f"  读取失败: {filename}: {e}")
    
    print(f"成功分析: {len(all_files) - failed_count}/{len(all_files)}")
    print(f"读取失败: {failed_count}")
    
    # 3. 显示所有序列
    print(f"\n3. 序列详情:")
    print("-" * 70)
    
    # 按序列号排序
    sorted_series = sorted(series_info.items(), key=lambda x: str(x[0]))
    
    brain_mac_candidates = []
    
    for series_num, info in sorted_series:
        count = info['count']
        desc = info['description']
        modality = info['modality']
        
        # 标记可能的候选
        marker = ""
        
        # 检查是否为Brain MAC相关序列
        is_brain_mac = ('brain' in desc.lower() and 'mac' in desc.lower()) or \
                       ('brain mac' in desc.lower()) or \
                       (modality == 'PT' and 'brain' in desc.lower())
        
        if is_brain_mac and count > 200:
            marker = " ⭐ Brain MAC!"
            brain_mac_candidates.append((series_num, info))
        elif count > 200:
            marker = " 🔍 大序列"
        elif is_brain_mac:
            marker = " 🧠 Brain/MAC"
        
        print(f"序列 {series_num:>3}: {count:>3}张 ({modality}) - {desc}{marker}")
    
    # 4. 处理候选序列
    print(f"\n4. Brain MAC候选序列:")
    
    if not brain_mac_candidates:
        print("❌ 未找到Brain MAC候选序列")
        print("\n尝试查找所有PET序列:")
        for series_num, info in sorted_series:
            if info['modality'] == 'PT' and info['count'] > 100:
                print(f"  序列 {series_num}: {info['count']}张 - {info['description']}")
                brain_mac_candidates.append((series_num, info))
    
    if not brain_mac_candidates:
        print("❌ 完全未找到合适的PET序列")
        print("\n显示最大的几个序列:")
        large_series = sorted(series_info.items(), key=lambda x: x[1]['count'], reverse=True)
        for i, (series_num, info) in enumerate(large_series[:5]):
            print(f"  第{i+1}大: 序列{series_num} - {info['count']}张 - {info['description']}")
        return
    
    # 5. 选择目标序列
    print(f"\n5. 处理所有Brain MAC序列:")
    for i, (series_num, info) in enumerate(brain_mac_candidates):
        print(f"  候选{i+1}: 序列{series_num} - {info['count']}张 - {info['description']}")
    
    # 处理所有Brain MAC序列
    processed_series = []
    for series_num, series_info in brain_mac_candidates:
        print(f"\n正在处理序列 {series_num}: {series_info['description']}")
        try:
            new_series_num, file_count = process_target_series(series_num, series_info)
            processed_series.append((series_num, new_series_num, file_count))
        except Exception as e:
            print(f"处理序列 {series_num} 失败: {e}")
    
    # 6. 汇总结果
    print(f"\n=== 处理汇总 ===")
    for orig_num, new_num, count in processed_series:
        print(f"原序列 {orig_num} -> 新序列 {new_num}: {count}张平均图像")
    
    print(f"\n📋 所有原始DICOM文件保持不变")
    print(f"📋 新增 {len(processed_series)} 个平均后的序列")

def process_target_series(series_num, series_info, base_dir):
    """
    处理选定的序列：将4个时相合并为1个
    """
    print(f"\n=== 处理序列 {series_num} ===")
    
    # 创建输出目录，以序列号命名
    output_dir = os.path.join(base_dir, f"processed_series_{series_num}")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    files = series_info['files']
    print(f"处理 {len(files)} 张图像")
    
    # 按实例号排序
    files.sort(key=lambda x: x['instance'])
    
    # 读取图像数据
    print("读取图像数据...")
    image_data = []
    image_shapes = []
    
    for i, file_info in enumerate(files):
        if i % 50 == 0:
            print(f"  读取 {i+1}/{len(files)}")
        
        try:
            ds = pydicom.dcmread(file_info['path'])
            img_array = ds.pixel_array.astype(np.float32)
            image_data.append(img_array)
            image_shapes.append(img_array.shape)
        except Exception as e:
            print(f"  读取失败: {file_info['filename']}")
            continue
    
    print(f"成功读取 {len(image_data)} 张图像")
    
    # 检查图像尺寸
    unique_shapes = list(set(image_shapes))
    print(f"图像尺寸种类: {len(unique_shapes)}")
    for shape in unique_shapes:
        count = image_shapes.count(shape)
        print(f"  {shape}: {count}张")
    
    # 计算平均
    print("计算4期平均...")
    
    # 找到最常见的图像尺寸（284张）
    shape_counts = {}
    for img in image_data:
        shape = img.shape
        shape_counts[shape] = shape_counts.get(shape, 0) + 1
    
    # 选择数量为284的尺寸，如果没有则选择最大的
    target_shape = None
    target_count = 0
    
    for shape, count in shape_counts.items():
        if count == 284:
            target_shape = shape
            target_count = count
            break
    
    if target_shape is None:
        # 如果没有284张，选择最接近284的
        for shape, count in sorted(shape_counts.items(), key=lambda x: abs(x[1] - 284)):
            if count >= 284:  # 确保有足够的图像
                target_shape = shape
                target_count = count
                break
    
    if target_shape is None:
        print("❌ 未找到足够的图像进行4期合并")
        return None, 0
    
    print(f"目标图像尺寸: {target_shape}，数量: {target_count}")
    
    # 只处理目标尺寸的图像
    target_images = [(i, img) for i, img in enumerate(image_data) if img.shape == target_shape]
    print(f"符合尺寸的图像: {len(target_images)}张")
    
    # 计算每期图像数量
    images_per_phase = len(target_images) // 4
    num_phases = 4
    
    if len(target_images) < 4:
        print("❌ 图像数量不足，无法分为4期")
        return None, 0
    
    print(f"图像分期: {num_phases}期，每期{images_per_phase}张")
    
    # 按原始实例号排序的目标尺寸图像
    sorted_target_images = []
    for orig_idx, img in target_images:
        file_info = files[orig_idx]
        sorted_target_images.append((file_info, img))
    
    # 按实例号重新排序
    sorted_target_images.sort(key=lambda x: x[0]['instance'])
    
    averaged_files = []
    
    for slice_idx in range(images_per_phase):
        if slice_idx % 10 == 0:
            print(f"  处理切片 {slice_idx+1}/{images_per_phase}")
        
        # 收集各期对应切片
        phase_slices = []
        base_file_info = None
        
        for phase in range(num_phases):
            img_idx = phase * images_per_phase + slice_idx
            if img_idx < len(sorted_target_images):
                file_info, img_data = sorted_target_images[img_idx]
                phase_slices.append(img_data)
                if base_file_info is None:
                    base_file_info = file_info
        
        if len(phase_slices) >= 1 and base_file_info:
            # 计算平均
            averaged = np.mean(phase_slices, axis=0)
            
            # 创建新的DICOM文件
            try:
                # 读取基础DICOM文件
                base_ds = pydicom.dcmread(base_file_info['path'])
                
                # 只更新像素数据，保留所有原始元数据
                base_ds.pixel_array[:] = averaged.astype(base_ds.pixel_array.dtype)
                
                # 保存DICOM文件（使用原始文件名或新文件名都可以）
                output_filename = f"averaged_{slice_idx+1:03d}.dcm"
                output_path = os.path.join(output_dir, output_filename)
                base_ds.save_as(output_path)
                
                averaged_files.append(output_path)
                
            except Exception as e:
                print(f"    DICOM保存失败 切片{slice_idx+1}: {e}")
                # 备用：保存为numpy文件
                np.save(os.path.join(output_dir, f"averaged_{slice_idx+1:03d}.npy"), averaged)
    
    print(f"\n✅ 处理完成!")
    print(f"📁 输出目录: {output_dir}")
    print(f"📄 生成 {len(averaged_files)} 个平均后的DICOM文件")
    print(f"ℹ️  元数据保持不变，仅更新像素数据")
    
    return series_num, len(averaged_files)

if __name__ == "__main__":
    # 分析多时相序列
    input_dir = r"E:\code\DICOM\13005"
    series_data, multiphase_series = analyze_multiphase_series(input_dir)
    
    # 如果检测到多时相序列，进行处理
    if multiphase_series and series_data:
        print("\n" + "=" * 80)
        print("🔧 开始处理多时相序列")
        print("=" * 80)
        
        # 收集所有文件信息
        all_files = {}
        for series_num in multiphase_series:
            info = series_data[series_num]
            files_info = []
            
            for filename in info['files']:
                filepath = os.path.join(input_dir, filename)
                try:
                    ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                    instance_num = getattr(ds, 'InstanceNumber', 0)
                    files_info.append({
                        'path': filepath,
                        'instance': instance_num,
                        'filename': filename
                    })
                except:
                    continue
            
            all_files[series_num] = {
                'count': len(files_info),
                'description': info['description'],
                'modality': info['modality'],
                'files': files_info
            }
        
        # 处理每个序列
        processed_series = []
        for series_num in multiphase_series:
            if series_num in all_files:
                print(f"\n正在处理序列 {series_num}: {all_files[series_num]['description']}")
                try:
                    new_series_num, file_count = process_target_series(series_num, all_files[series_num], input_dir)
                    if new_series_num:
                        processed_series.append((series_num, new_series_num, file_count))
                except Exception as e:
                    print(f"❌ 处理序列 {series_num} 失败: {e}")
        
        # 汇总结果
        print("\n" + "=" * 80)
        print("📊 处理汇总")
        print("=" * 80)
        for orig_num, kept_num, count in processed_series:
            print(f"✅ 序列 {orig_num}: 生成 {count} 张平均图像 (元数据不变)")
        
        print(f"\n📋 所有原始DICOM文件保持不变")
        print(f"📋 新增 {len(processed_series)} 个平均后的序列")
        print(f"ℹ️  平均后的文件保留原始序列号和其他元数据")