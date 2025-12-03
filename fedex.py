import streamlit as st
import requests
import base64
import json
import pandas as pd
from typing import Optional, Dict, Any, List

# 页面配置
st.set_page_config(
    page_title="Beans.ai Enterprise API v2",
    page_icon="📍",
    layout="wide"
)

def get_auth_header(key: str) -> str:
    """生成 Basic Authentication header"""
    # 如果已经是 Basic 格式，直接返回
    if key.strip().startswith("Basic "):
        return key.strip()
    
    # 如果 key 包含冒号，说明是 key:secret 格式，直接使用
    # 否则使用 key:key 格式
    if ':' in key:
        credentials = key
    else:
        credentials = f"{key}:{key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"

def make_request(url: str, headers: Dict[str, str], params: Optional[Dict] = None) -> Dict[str, Any]:
    """发送 API 请求"""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"请求错误: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                st.error(f"响应内容: {e.response.text}")
            except:
                pass
        return {}

def extract_field_value(data: Any, field_path: str) -> Any:
    """从嵌套的字典/列表中提取字段值"""
    try:
        parts = field_path.split('.')
        current = data
        
        for part in parts:
            if '[' in part and ']' in part:
                # 处理数组索引，如 dims[3]
                key = part[:part.index('[')]
                index = int(part[part.index('[')+1:part.index(']')])
                if isinstance(current, dict) and key in current:
                    current = current[key]
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                else:
                    return None
            else:
                # 普通键
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
        
        return current
    except:
        return None

def find_field_in_dict(data: Any, field_names: List[str], case_sensitive: bool = False) -> Any:
    """在字典中查找字段，尝试多种可能的字段名"""
    if not isinstance(data, dict):
        return None
    
    for field_name in field_names:
        if case_sensitive:
            if field_name in data:
                return data[field_name]
        else:
            # 不区分大小写查找
            for key, value in data.items():
                if str(key).upper() == field_name.upper():
                    return value
    
    return None

def search_fields_recursive(data: Any, search_terms: List[str], path: str = "") -> List[Dict[str, Any]]:
    """递归搜索包含特定关键词的字段"""
    results = []
    search_terms_upper = [term.upper() for term in search_terms]
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            key_upper = str(key).upper()
            
            # 检查键名是否包含搜索词
            for term in search_terms_upper:
                if term in key_upper:
                    results.append({
                        "路径": current_path,
                        "字段名": key,
                        "值": value,
                        "类型": type(value).__name__
                    })
                    break
            
            # 递归搜索嵌套结构
            if isinstance(value, (dict, list)):
                results.extend(search_fields_recursive(value, search_terms, current_path))
    
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            current_path = f"{path}[{idx}]"
            if isinstance(item, (dict, list)):
                results.extend(search_fields_recursive(item, search_terms, current_path))
    
    return results

def parse_dimensions(dims_v_str: str) -> Dict[str, str]:
    """从 dimensions.dims[3].v 中解析 length, width, height
    格式: pd:43.74×28.03×5.51
    - length: pd: 后面，第一个 × 之前的值
    - width: 两个 × 之间的值
    - height: 第二个 × 之后的值
    """
    result = {'length': '', 'width': '', 'height': ''}
    
    if not dims_v_str or not isinstance(dims_v_str, str):
        return result
    
    try:
        # 查找 "pd:" 的位置
        if 'pd:' in dims_v_str.lower():
            # 找到 pd: 后面的部分
            pd_index = dims_v_str.lower().find('pd:')
            if pd_index != -1:
                # 提取 pd: 后面的内容
                after_pd = dims_v_str[pd_index + 3:].strip()
                
                # 使用 × 分割（可能是 × 或 x）
                # 先尝试 × (乘号)
                if '×' in after_pd:
                    parts = after_pd.split('×')
                elif 'x' in after_pd:
                    parts = after_pd.split('x')
                elif 'X' in after_pd:
                    parts = after_pd.split('X')
                else:
                    return result
                
                if len(parts) >= 3:
                    result['length'] = parts[0].strip()
                    result['width'] = parts[1].strip()
                    result['height'] = parts[2].strip()
                elif len(parts) == 2:
                    result['length'] = parts[0].strip()
                    result['width'] = parts[1].strip()
        else:
            # 如果没有 pd:，直接尝试用 × 分割
            if '×' in dims_v_str:
                parts = dims_v_str.split('×')
            elif 'x' in dims_v_str:
                parts = dims_v_str.split('x')
            elif 'X' in dims_v_str:
                parts = dims_v_str.split('X')
            else:
                return result
            
            if len(parts) >= 3:
                result['length'] = parts[0].strip()
                result['width'] = parts[1].strip()
                result['height'] = parts[2].strip()
            elif len(parts) == 2:
                result['length'] = parts[0].strip()
                result['width'] = parts[1].strip()
    except Exception:
        pass
    
    return result

def extract_required_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取用户需要的特定字段"""
    fields = {}
    
    # trackingId
    fields['trackingId'] = result.get('trackingId', '') or result.get('tracking_id', '')
    
    # WEIGHT - 直接从 dimensions.dims[0].v 获取
    weight = extract_field_value(result, 'dimensions.dims[0].v')
    fields['WEIGHT'] = weight if weight is not None else ''
    
    # VOLUME - 直接从 dimensions.dims[1].v 获取
    volume = extract_field_value(result, 'dimensions.dims[1].v')
    fields['VOLUME'] = volume if volume is not None else ''
    
    # dimensions.dims[3].t
    dims_t = extract_field_value(result, 'dimensions.dims[3].t')
    fields['dimensions.dims[3].t'] = dims_t if dims_t is not None else 'NONE'
    
    # dimensions.dims[3].v
    dims_v = extract_field_value(result, 'dimensions.dims[3].v')
    fields['dimensions.dims[3].v'] = dims_v if dims_v is not None else ''
    
    # 从 dimensions.dims[3].v 解析 length, width, height
    if dims_v:
        parsed_dims = parse_dimensions(str(dims_v))
        fields['length'] = parsed_dims.get('length', '')
        fields['width'] = parsed_dims.get('width', '')
        fields['height'] = parsed_dims.get('height', '')
    else:
        fields['length'] = ''
        fields['width'] = ''
        fields['height'] = ''
    
    # 同时提取其他 dims 的值，便于调试
    dims_0_v = extract_field_value(result, 'dimensions.dims[0].v')
    dims_1_v = extract_field_value(result, 'dimensions.dims[1].v')
    fields['dimensions.dims[0].v'] = dims_0_v if dims_0_v is not None else ''
    fields['dimensions.dims[1].v'] = dims_1_v if dims_1_v is not None else ''
    
    # shipperNote
    fields['shipperNote'] = result.get('shipperNote', '') or result.get('shipper_note', '')
    
    # address
    fields['address'] = result.get('address', '')
    
    # customerName
    fields['customerName'] = result.get('customerName', '') or result.get('customer_name', '')
    
    # customerPhone
    fields['customerPhone'] = result.get('customerPhone', '') or result.get('customer_phone', '')
    
    return fields

def format_fields_recursive(data: Any, prefix: str = "", depth: int = 0, max_depth: int = 10) -> List[str]:
    """递归解析 JSON 数据，返回格式化的字段列表（字段：内容格式）"""
    fields = []
    indent = "  " * depth
    
    if depth > max_depth:
        return fields
    
    if isinstance(data, dict):
        for key, value in data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict) and value:
                # 对象类型，先显示字段名，然后递归显示内容
                fields.append(f"{indent}{field_path}:")
                fields.extend(format_fields_recursive(value, field_path, depth + 1, max_depth))
            elif isinstance(value, list) and value:
                # 数组类型
                fields.append(f"{indent}{field_path}: [数组，共 {len(value)} 项]")
                # 显示数组中每个元素
                for idx, item in enumerate(value):
                    if isinstance(item, (dict, list)):
                        fields.append(f"{indent}  [{field_path}[{idx}]]:")
                        fields.extend(format_fields_recursive(item, f"{field_path}[{idx}]", depth + 2, max_depth))
                    else:
                        fields.append(f"{indent}  {field_path}[{idx}]: {item}")
            elif value is None:
                fields.append(f"{indent}{field_path}: null")
            else:
                # 简单值直接显示
                display_value = str(value)
                # 对于长文本，截断显示
                if len(display_value) > 200:
                    display_value = display_value[:200] + "..."
                fields.append(f"{indent}{field_path}: {display_value}")
    
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            if isinstance(item, (dict, list)):
                fields.append(f"{indent}{prefix}[{idx}]:")
                fields.extend(format_fields_recursive(item, f"{prefix}[{idx}]", depth + 1, max_depth))
            else:
                fields.append(f"{indent}{prefix}[{idx}]: {item}")
    
    else:
        display_value = str(data)
        if len(display_value) > 200:
            display_value = display_value[:200] + "..."
        if prefix:
            fields.append(f"{indent}{prefix}: {display_value}")
        else:
            fields.append(f"{indent}{display_value}")
    
    return fields

# 主标题
st.title("📍 Beans.ai Tracking ID 查询工具")
st.markdown("---")

# 🔐 认证：从 Streamlit Secrets 读取，不在页面上输入
# 在 Streamlit Cloud 的 Secrets 中配置：
# BEANS_API_AUTH_BASIC = "Basic xxxxxx"  或者是 key / key:secret
secret_key = st.secrets.get("BEANS_API_AUTH_BASIC", "").strip()

if not secret_key:
    st.error("❌ 未在 Secrets 中找到 BEANS_API_AUTH_BASIC，请在 Streamlit 控制台的 Secrets 中配置。")
    st.stop()

auth_header = get_auth_header(secret_key)

# Tracking ID 输入
st.header("📋 Tracking ID 查询")

tracking_ids_text = st.text_area(
    "粘贴 Tracking ID（每行一个，或单个）*",
    height=150,
    placeholder="例如：\nABCD\nEFGH\nIJKL\n\n或者单个：\nABCD",
    help="可以粘贴单个或多个 Tracking ID，每行一个。使用 Get Stop By Tracking ID API 查询。"
)

if st.button("🔍 查询", type="primary", use_container_width=True):
    if not tracking_ids_text.strip():
        st.error("❌ 请输入 Tracking ID")
    else:
        # 解析 Tracking IDs
        tracking_ids = [tid.strip() for tid in tracking_ids_text.strip().split('\n') if tid.strip()]
        
        if len(tracking_ids) == 1:
            st.info(f"正在查询 1 个 Tracking ID: {tracking_ids[0]}")
        else:
            st.info(f"正在查询 {len(tracking_ids)} 个 Tracking ID")
        
        # 处理每个 Tracking ID
        all_results = []
        summary_rows = []  # 汇总到一张表里的行
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 使用 API: Get Stop By Tracking ID
        base_url = "https://isp.beans.ai/enterprise/v1/lists/item_by_tracking_id"
        
        for idx, tracking_id in enumerate(tracking_ids):
            status_text.text(f"处理中: {idx + 1}/{len(tracking_ids)} - {tracking_id}")
            progress_bar.progress((idx + 1) / len(tracking_ids))
            
            params = {
                "tracking_id": tracking_id
            }
            
            headers = {
                "Authorization": auth_header
            }
            
            result = make_request(base_url, headers, params)
            
            record = {
                "tracking_id": tracking_id,
                "status": "成功" if result else "失败",
                "result": result,
            }
            all_results.append(record)

            # 如果有结果，提取为“汇总表”的一行
            if result:
                required_fields = extract_required_fields(result)
                row = {
                    # 统一成 Excel 表头形式：一行一个 tracking
                    "trackingId": tracking_id,  # 以用户输入为准
                    "WEIGHT": required_fields.get("WEIGHT", ""),
                    "VOLUME": required_fields.get("VOLUME", ""),
                    "length": required_fields.get("length", ""),
                    "width": required_fields.get("width", ""),
                    "height": required_fields.get("height", ""),
                    "shipperNote": required_fields.get("shipperNote", ""),
                    "address": required_fields.get("address", ""),
                    "customerName": required_fields.get("customerName", ""),
                    "customerPhone": required_fields.get("customerPhone", ""),
                    "dimensions.dims[3].t": required_fields.get("dimensions.dims[3].t", ""),
                    "dimensions.dims[3].v": required_fields.get("dimensions.dims[3].v", ""),
                    "dimensions.dims[0].v": required_fields.get("dimensions.dims[0].v", ""),
                    "dimensions.dims[1].v": required_fields.get("dimensions.dims[1].v", ""),
                }
                summary_rows.append(row)
        
        progress_bar.empty()
        status_text.empty()
        
        st.markdown("---")
        st.success(f"✅ 查询完成！共处理 {len(tracking_ids)} 个 Tracking ID")

        # 📊 先给一张 “所有 tracking 汇总表”（方便直接导出到 Excel）
        if summary_rows:
            st.subheader("📊 所有 Tracking ID 汇总表（Excel 表头格式）")

            # 确保列顺序固定
            columns_order = [
                "trackingId",
                "WEIGHT", "VOLUME",
                "length", "width", "height",
                "shipperNote", "address",
                "customerName", "customerPhone",
                "dimensions.dims[3].t",
                "dimensions.dims[3].v",
                "dimensions.dims[0].v",
                "dimensions.dims[1].v",
            ]
            df_summary = pd.DataFrame(summary_rows)

            # 保证即便有些列缺失也不会报错
            for col in columns_order:
                if col not in df_summary.columns:
                    df_summary[col] = ""

            df_summary = df_summary[columns_order]

            st.dataframe(df_summary, use_container_width=True)

            csv_all = df_summary.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 下载所有 Tracking 的汇总 CSV（可直接用 Excel 打开）",
                data=csv_all,
                file_name="beans_tracking_summary.csv",
                mime="text/csv",
            )

        # 下面保留每个 tracking 的详细信息 / 调试信息（如果你不需要可以整体删掉这一段）
        st.markdown("---")
        st.subheader("🔎 每个 Tracking ID 详细结果")

        for idx, result_item in enumerate(all_results):
            tracking_id = result_item["tracking_id"]
            result = result_item.get("result", {})
            
            if result:
                st.markdown("---")
                st.markdown(f"### 📋 Tracking ID: `{tracking_id}` - 查询结果")
                
                # 提取需要的字段
                required_fields = extract_required_fields(result)
                
                # 显示关键字段表格
                st.markdown("#### 📊 关键字段（单条查看用）")
                
                weight_value = required_fields.get('WEIGHT', '')
                volume_value = required_fields.get('VOLUME', '')
                
                # 如果没找到，显示调试信息并搜索相关字段
                if not weight_value or not volume_value:
                    with st.expander("🔍 调试信息：查找 WEIGHT 和 VOLUME 字段", expanded=False):
                        st.warning("⚠️ WEIGHT 或 VOLUME 字段未找到，正在搜索相关字段...")
                        search_results = search_fields_recursive(result, ['weight', 'volume'])
                        if search_results:
                            st.info(f"找到 {len(search_results)} 个相关字段：")
                            search_df = pd.DataFrame(search_results)
                            st.dataframe(search_df, use_container_width=True)
                            st.caption("💡 提示：如果看到相关字段，请告诉我实际的字段路径，我会更新代码")
                        else:
                            st.info("未找到包含 'weight' 或 'volume' 的字段。请查看原始 JSON 数据。")
                
                fields_df = pd.DataFrame([
                    {"字段": "trackingId", "值": tracking_id},
                    {"字段": "WEIGHT", "值": weight_value if weight_value else "⚠️ 未找到"},
                    {"字段": "VOLUME", "值": volume_value if volume_value else "⚠️ 未找到"},
                    {"字段": "length", "值": required_fields.get('length', '')},
                    {"字段": "width", "值": required_fields.get('width', '')},
                    {"字段": "height", "值": required_fields.get('height', '')},
                    {"字段": "shipperNote", "值": required_fields.get('shipperNote', '')},
                    {"字段": "address", "值": required_fields.get('address', '')},
                    {"字段": "customerName", "值": required_fields.get('customerName', '')},
                    {"字段": "customerPhone", "值": required_fields.get('customerPhone', '')},
                ])
                st.dataframe(fields_df, use_container_width=True, hide_index=True)
                
                # 下载当前 tracking 的关键字段（按原来逻辑保留）
                csv_data = fields_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label=f"📥 下载该 Tracking 的关键字段 (CSV) - {tracking_id}",
                    data=csv_data,
                    file_name=f"fields_{tracking_id}.csv",
                    mime="text/csv",
                    key=f"download_csv_{tracking_id}_{idx}"
                )
                
                # 所有字段列表（文本）
                st.markdown("#### 📋 所有字段列表（缩进展示）")
                fields_list = format_fields_recursive(result)
                fields_text = "\n".join(fields_list)
                st.code(fields_text, language="text")
                
                st.download_button(
                    label=f"📥 下载该 Tracking 的所有字段列表 (TXT) - {tracking_id}",
                    data=fields_text,
                    file_name=f"all_fields_{tracking_id}.txt",
                    mime="text/plain",
                    key=f"download_all_{tracking_id}_{idx}"
                )
                
                # 原始 JSON
                with st.expander(f"📄 查看原始 JSON 数据 - {tracking_id}"):
                    st.json(result)
            else:
                st.warning(f"⚠️ Tracking ID `{tracking_id}` 查询失败或无数据")
                st.markdown("---")

# 页脚
st.markdown("---")
st.markdown("### 📖 使用说明")
st.markdown("""
1. 在 **Streamlit 控制台的 Secrets** 中配置 `BEANS_API_AUTH_BASIC`（不要在页面上填 key）
2. 在文本框中粘贴 **多个 Tracking ID**（每行一个）
3. 点击查询按钮，会生成：
   - 一张所有 Tracking 的 **汇总表**（表头即 Excel 列名）
   - 每个 Tracking 的详细字段、调试信息和原始 JSON

**API 信息**: 
- 使用 **Get Stop By Tracking ID** API
- 端点: `https://isp.beans.ai/enterprise/v1/lists/item_by_tracking_id`
- 只需提供 Tracking ID

**注意**: 所有 API 请求都需要有效的认证信息。请确保您已在 Secrets 中正确配置密钥。
""")
