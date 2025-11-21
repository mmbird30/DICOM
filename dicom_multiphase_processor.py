"""
DICOM多时相序列处理通用脚本
功能：自动识别、平均处理多时相序列，并合并到最终数据集
"""

import os
import shutil
import pydicom
import numpy as np
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# 常量定义
MULTIPHASE_RATIO_THRESHOLD = 0.8  # 多时相切片占比阈值（80%）
AVG_PHASES_THRESHOLD = 1.5        # 平均时相数阈值
SUPPORTED_MODALITIES = ['PT', 'NM']  # 支持的模态：PET和核医学
PROGRESS_INTERVAL = 500           # 进度显示间隔
MAX_ERROR_DISPLAY = 5             # 最多显示的错误数量


class DICOMMultiphaseProcessor:
    """
    DICOM多时相序列处理器
    
    专门用于处理PET/NM模态的多时相动态扫描序列。
    功能包括：
    1. 自动识别多时相序列
    2. 计算时相平均值
    3. 合并处理结果到最终数据集
    
    Attributes:
        input_dir (str): 输入DICOM目录路径
        output_dir (str): 输出目录路径
        processed_dir (str): 临时处理目录路径
        processed_dirs (Dict[str, str]): 序列UID到目录名的映射
    """
    
    def __init__(self, input_dir: str, output_dir: Optional[str] = None):
        """
        初始化处理器
        
        Args:
            input_dir: 原始DICOM目录
            output_dir: 最终输出目录（默认在原目录下创建 _processed 后缀）
        """
        self.input_dir = input_dir
        self.output_dir = output_dir or f"{input_dir}_out"
        self.processed_dir = os.path.join(input_dir, "tmp_proc")
        self.processed_dirs = {}  # 存储 series_uid -> dir_name 的映射
        
    def analyze_multiphase(self) -> Tuple[Optional[Dict], List[str]]:
        """分析并识别多时相序列
        
        Returns:
            Tuple[Optional[Dict], List[str]]: (序列数据字典, 多时相序列UID列表)
        """
        print("=" * 80)
        print("📋 步骤1: 分析多时相序列")
        print("=" * 80)
        
        if not os.path.exists(self.input_dir):
            print(f"❌ 目录不存在: {self.input_dir}")
            return None, []
        
        print(f"📁 分析目录: {self.input_dir}")
        all_files = [f for f in os.listdir(self.input_dir) 
                     if os.path.isfile(os.path.join(self.input_dir, f))]
        print(f"📊 文件总数: {len(all_files)}\n")
        
        if len(all_files) == 0:
            print("❌ 目录为空!")
            return None, []
        
        # 收集序列信息
        print("🔍 扫描文件...")
        series_data = defaultdict(lambda: {
            'description': '',
            'modality': '',
            'series_number': None,
            'files': [],
            'slice_positions': defaultdict(list),
            'instance_numbers': []
        })
        
        failed_count = 0
        for i, filename in enumerate(all_files):
            if (i + 1) % PROGRESS_INTERVAL == 0:
                print(f"  进度: {i + 1}/{len(all_files)}")
            
            try:
                filepath = os.path.join(self.input_dir, filename)
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                
                # 使用 SeriesInstanceUID 作为唯一标识
                series_uid = getattr(ds, 'SeriesInstanceUID', None)
                if not series_uid:
                    continue
                
                series_num = getattr(ds, 'SeriesNumber', 'Unknown')
                series_desc = getattr(ds, 'SeriesDescription', 'Unknown')
                modality = getattr(ds, 'Modality', 'Unknown')
                instance_num = getattr(ds, 'InstanceNumber', None)
                
                # 获取切片位置
                slice_location = getattr(ds, 'SliceLocation', None)
                image_position = getattr(ds, 'ImagePositionPatient', None)
                
                if image_position and len(image_position) >= 3:
                    z_pos = round(float(image_position[2]), 2)
                elif slice_location is not None:
                    z_pos = round(float(slice_location), 2)
                else:
                    z_pos = None
                
                # 使用 SeriesInstanceUID 作为键
                series_data[series_uid]['description'] = series_desc
                series_data[series_uid]['modality'] = modality
                series_data[series_uid]['series_number'] = series_num
                series_data[series_uid]['files'].append(filename)
                series_data[series_uid]['instance_numbers'].append(instance_num)
                
                if z_pos is not None:
                    series_data[series_uid]['slice_positions'][z_pos].append({
                        'instance': instance_num,
                        'filename': filename
                    })
            
            except (FileNotFoundError, PermissionError, pydicom.errors.InvalidDicomError) as e:
                failed_count += 1
                if failed_count <= MAX_ERROR_DISPLAY:
                    print(f"  ⚠️  读取失败: {filename} ({type(e).__name__})")
        
        print(f"✅ 扫描完成")
        if failed_count > 0:
            print(f"⚠️  共 {failed_count} 个文件读取失败\n")
        
        # 分析多时相
        print("\n" + "=" * 80)
        print("📊 序列分析报告")
        print("=" * 80)
        
        multiphase_series = []
        
        for series_uid in sorted(series_data.keys()):
            info = series_data[series_uid]
            series_num = info['series_number']
            series_desc = info['description']
            total_images = len(info['files'])
            unique_slices = len(info['slice_positions'])
            
            if unique_slices > 0:
                phases_per_slice = [len(instances) 
                                   for instances in info['slice_positions'].values()]
                avg_phases = np.mean(phases_per_slice)
                max_phases = max(phases_per_slice)
                min_phases = min(phases_per_slice)
                
                # 更严格的多时相判断：
                # 1. 模态必须是PT（PET）或NM（核医学）
                # 2. 最大时相数 > 1
                # 3. 至少80%的切片有多个时相（避免误判）
                # 4. 平均时相数 >= 1.5
                modality = info['modality']
                is_supported_modality = modality in SUPPORTED_MODALITIES
                
                multiphase_slice_count = sum(1 for p in phases_per_slice if p > 1)
                multiphase_ratio = multiphase_slice_count / len(phases_per_slice)
                
                is_multiphase = (is_supported_modality and
                                max_phases > 1 and 
                                multiphase_ratio >= MULTIPHASE_RATIO_THRESHOLD and 
                                avg_phases >= AVG_PHASES_THRESHOLD)
            else:
                avg_phases = max_phases = min_phases = 0
                multiphase_ratio = 0
                is_multiphase = False
            
            marker = " 🔴 [多时相]" if is_multiphase else ""
            
            print(f"\n【序列 {series_num} - {series_desc[:30]}】{marker}")
            print(f"  描述: {info['description']}")
            print(f"  模态: {info['modality']}")
            print(f"  总图像数: {total_images}")
            print(f"  唯一切片数: {unique_slices}")
            
            if unique_slices > 0:
                print(f"  每切片时相数: 平均{avg_phases:.1f}, 最大{max_phases}, 最小{min_phases}")
                print(f"  多时相切片占比: {multiphase_ratio*100:.1f}%")
                
                if is_multiphase:
                    multiphase_series.append(series_uid)
                    print(f"  ✅ 检测到多时相序列（约{int(avg_phases)}期动态扫描）")
                elif max_phases > 1:
                    threshold_percent = int(MULTIPHASE_RATIO_THRESHOLD * 100)
                    print(f"  ⚠️  部分切片有多时相，但占比不足（{multiphase_ratio*100:.0f}% < {threshold_percent}%），不处理")
        
        # 总结
        print("\n" + "=" * 80)
        print(f"总序列数: {len(series_data)}")
        print(f"多时相序列数: {len(multiphase_series)}")
        
        if multiphase_series:
            print(f"\n🔴 检测到 {len(multiphase_series)} 个多时相序列")
        else:
            print("\n✅ 未检测到多时相序列")
        
        return series_data, multiphase_series
    
    def process_series(self, series_uid: str, series_info: Dict) -> Tuple[int, str]:
        """处理单个序列的多时相平均
        
        Args:
            series_uid: 序列唯一标识符
            series_info: 序列信息字典
            
        Returns:
            Tuple[int, str]: (生成的文件数量, 输出目录名)
        """
        series_num = series_info['series_number']
        series_desc = series_info['description'][:30]
        
        print(f"\n{'='*60}")
        print(f"处理序列 {series_num} - {series_desc}")
        print(f"{'='*60}")
        
        # 创建临时输出目录
        # 使用序列号和描述的哈希值作为目录名
        dir_name = f"s{series_num}_{abs(hash(series_uid)) % 10000}"
        series_output_dir = os.path.join(self.processed_dir, dir_name)
        Path(series_output_dir).mkdir(parents=True, exist_ok=True)
        
        # 收集文件信息
        files = []
        for filename in series_info['files']:
            filepath = os.path.join(self.input_dir, filename)
            try:
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                instance_num = getattr(ds, 'InstanceNumber', 0)
                files.append({
                    'path': filepath,
                    'instance': instance_num,
                    'filename': filename
                })
            except (FileNotFoundError, PermissionError, pydicom.errors.InvalidDicomError):
                continue
        
        files.sort(key=lambda x: x['instance'])
        print(f"处理 {len(files)} 张图像")
        
        # 读取图像数据
        print("读取图像数据...")
        image_data = []
        
        for i, file_info in enumerate(files):
            if i % 50 == 0:
                print(f"  读取 {i+1}/{len(files)}")
            
            try:
                ds = pydicom.dcmread(file_info['path'])
                img_array = ds.pixel_array.astype(np.float32)
                image_data.append((file_info, img_array, img_array.shape))
            except Exception as e:
                print(f"  ⚠️  读取失败: {file_info['filename']}")
                continue
        
        print(f"成功读取 {len(image_data)} 张图像")
        
        # 检查图像尺寸并分组
        shape_groups = defaultdict(list)
        for file_info, img_array, shape in image_data:
            shape_groups[shape].append((file_info, img_array))
        
        print(f"\n图像尺寸分析:")
        for shape, imgs in shape_groups.items():
            print(f"  {shape}: {len(imgs)}张")
        
        # 选择最大的尺寸组进行处理
        if not shape_groups:
            print("❌ 没有有效的图像数据")
            return 0, ""
        
        target_shape = max(shape_groups.keys(), key=lambda s: len(shape_groups[s]))
        image_data = shape_groups[target_shape]
        
        print(f"\n选择处理尺寸: {target_shape}, 共{len(image_data)}张图像")
        
        # 判断时相数
        total_images = len(image_data)
        unique_slices = len(series_info['slice_positions'])
        
        if unique_slices == 0:
            print("❌ 无法确定切片数量")
            return 0, ""
        
        num_phases = total_images // unique_slices
        images_per_phase = unique_slices
        
        print(f"检测到: {num_phases}期, 每期{images_per_phase}张")
        
        if num_phases < 2:
            print("❌ 时相数小于2，无需处理")
            return 0, ""
        
        # 计算平均
        print(f"计算{num_phases}期平均...")
        averaged_files = []
        
        for slice_idx in range(images_per_phase):
            if slice_idx % 10 == 0:
                print(f"  处理切片 {slice_idx+1}/{images_per_phase}")
            
            # 收集各期对应切片
            phase_slices = []
            base_file_info = None
            
            for phase in range(num_phases):
                img_idx = phase * images_per_phase + slice_idx
                if img_idx < len(image_data):
                    file_info, img_array = image_data[img_idx]
                    phase_slices.append(img_array)
                    if base_file_info is None:
                        base_file_info = file_info
            
            if len(phase_slices) >= 1 and base_file_info:
                # 检查所有切片是否尺寸一致
                if len(set(img.shape for img in phase_slices)) > 1:
                    print(f"  ⚠️  跳过切片{slice_idx+1}: 尺寸不一致")
                    continue
                
                # 计算平均
                averaged = np.mean(phase_slices, axis=0)
                
                try:
                    base_ds = pydicom.dcmread(base_file_info['path'])
                    base_ds.pixel_array[:] = averaged.astype(base_ds.pixel_array.dtype)
                    
                    output_filename = f"avg_{slice_idx+1:04d}.dcm"
                    output_path = os.path.join(series_output_dir, output_filename)
                    base_ds.save_as(output_path)
                    
                    averaged_files.append(output_path)
                except Exception as e:
                    print(f"  ⚠️  保存失败 切片{slice_idx+1}: {e}")
        
        print(f"✅ 生成 {len(averaged_files)} 个平均文件")
        return len(averaged_files), dir_name
    
    def merge_results(self, series_data: Dict, multiphase_series: List[str]) -> None:
        """合并结果：排除多时相原文件，添加平均文件
        
        Args:
            series_data: 序列数据字典
            multiphase_series: 多时相序列UID列表
        """
        print("\n" + "=" * 80)
        print("📋 步骤3: 合并最终数据集")
        print("=" * 80)
        
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        
        # 构建要排除的文件集合（使用 SeriesInstanceUID）
        excluded_series_uids = set(multiphase_series)
        
        # 分析原始文件
        print("分析原始文件...")
        all_files = [f for f in os.listdir(self.input_dir) 
                     if os.path.isfile(os.path.join(self.input_dir, f))]
        
        files_to_copy = []
        excluded_count = 0
        
        for filename in all_files:
            try:
                filepath = os.path.join(self.input_dir, filename)
                ds = pydicom.dcmread(filepath, stop_before_pixels=True)
                series_uid = getattr(ds, 'SeriesInstanceUID', None)
                
                if series_uid in excluded_series_uids:
                    excluded_count += 1
                else:
                    files_to_copy.append(filename)
            except (FileNotFoundError, PermissionError, pydicom.errors.InvalidDicomError):
                files_to_copy.append(filename)  # 无法读取的文件默认保留
        
        print(f"  保留文件: {len(files_to_copy)}")
        print(f"  排除文件: {excluded_count}")
        
        # 复制保留的文件
        print("\n复制保留的文件...")
        for i, filename in enumerate(files_to_copy):
            if i % 200 == 0:
                print(f"  进度: {i}/{len(files_to_copy)}")
            
            src_path = os.path.join(self.input_dir, filename)
            dst_path = os.path.join(self.output_dir, filename)
            
            try:
                shutil.copy2(src_path, dst_path)
            except Exception as e:
                print(f"  ⚠️  复制失败: {filename}")
        
        # 添加平均文件
        print("\n添加平均文件...")
        added_count = 0
        
        for series_uid, dir_name in self.processed_dirs.items():
            series_dir = os.path.join(self.processed_dir, dir_name)
            if not os.path.exists(series_dir):
                continue
            
            series_info = series_data[series_uid]
            series_num = series_info['series_number']
            
            avg_files = [f for f in os.listdir(series_dir) if f.endswith('.dcm')]
            print(f"  序列{series_num} - {series_info['description'][:30]}: {len(avg_files)}张")
            
            for i, filename in enumerate(avg_files):
                src_path = os.path.join(series_dir, filename)
                new_filename = f"proc_s{series_num}_{i+1:04d}.dcm"
                dst_path = os.path.join(self.output_dir, new_filename)
                
                try:
                    shutil.copy2(src_path, dst_path)
                    added_count += 1
                except Exception as e:
                    print(f"  ⚠️  复制失败: {filename}")
        
        # 清理临时目录
        if os.path.exists(self.processed_dir):
            shutil.rmtree(self.processed_dir)
        
        # 统计最终结果
        final_files = os.listdir(self.output_dir)
        
        print("\n" + "=" * 80)
        print("✅ 处理完成!")
        print("=" * 80)
        print(f"📁 输出目录: {self.output_dir}")
        print(f"📊 文件统计:")
        print(f"   原始保留: {len(files_to_copy)} 文件")
        print(f"   新增平均: {added_count} 文件")
        print(f"   最终总计: {len(final_files)} 文件")
    
    def run(self) -> None:
        """执行完整的多时相处理流程
        
        工作流程：
        1. 分析并识别多时相序列
        2. 处理每个多时相序列（计算平均）
        3. 合并处理结果到最终数据集
        """
        print("\n" + "🔬" * 40)
        print("DICOM多时相序列处理器")
        print("🔬" * 40 + "\n")
        
        # 步骤1: 分析
        series_data, multiphase_series = self.analyze_multiphase()
        
        if not multiphase_series:
            print("\n没有检测到多时相序列，无需处理")
            return
        
        # 步骤2: 处理多时相序列
        print("\n" + "=" * 80)
        print("📋 步骤2: 处理多时相序列")
        print("=" * 80)
        
        processed_count = 0
        for series_uid in multiphase_series:
            result = self.process_series(series_uid, series_data[series_uid])
            if isinstance(result, tuple) and result[0] > 0:
                count, dir_name = result
                self.processed_dirs[series_uid] = dir_name
                processed_count += 1
        
        print(f"\n✅ 成功处理 {processed_count}/{len(multiphase_series)} 个序列")
        
        # 步骤3: 合并
        self.merge_results(series_data, multiphase_series)


def main() -> None:
    """
    主函数 - 交互式输入路径
    
    提供用户友好的交互界面，允许用户输入路径并执行处理。
    """
    
    print("=" * 80)
    print("DICOM多时相序列处理器")
    print("=" * 80)
    
    # 输入目录
    print("\n请输入DICOM文件目录路径:")
    print("(例如: E:\\code\\DICOM\\13005)")
    input_dir = input("输入目录: ").strip().strip('"').strip("'")
    
    if not input_dir:
        print("❌ 未输入目录路径")
        input("按回车键退出...")
        return
    
    if not os.path.exists(input_dir):
        print(f"❌ 目录不存在: {input_dir}")
        input("按回车键退出...")
        return
    
    if not os.path.isdir(input_dir):
        print(f"❌ 路径不是目录: {input_dir}")
        input("按回车键退出...")
        return
    
    # 输出目录（可选）
    print("\n请输入输出目录路径 (直接回车则默认为输入目录_processed):")
    output_dir = input("输出目录 [可选]: ").strip().strip('"').strip("'")
    
    if not output_dir:
        output_dir = None
        print(f"✅ 将使用默认输出目录: {input_dir}_out")
    else:
        print(f"✅ 输出目录: {output_dir}")
    
    print("\n" + "=" * 80)
    input("按回车键开始处理...")
    
    processor = DICOMMultiphaseProcessor(input_dir, output_dir)
    processor.run()
    
    print("\n" + "=" * 80)
    input("处理完成！按回车键退出...")


if __name__ == "__main__":
    main()
