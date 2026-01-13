"""
标准化数据库中的 fact key
将 user_name, user_name_v2 -> name
将 occupation_v2 -> occupation
将 age_v2 -> age
"""
import sqlite3

def print_separator(title=""):
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print('='*70)
    else:
        print('='*70)

def standardize_keys():
    """标准化数据库中的 key 名称"""
    print_separator("🔧 标准化 fact key")
    
    db_path = "memory.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 定义 key 映射规则
    key_mappings = {
        'user_name': 'name',
        'user_name_v2': 'name',
        'occupation_v2': 'occupation',
        'age_v2': 'age',
    }
    
    print("\n📋 Key 映射规则:")
    for old_key, new_key in key_mappings.items():
        print(f"  {old_key} → {new_key}")
    
    # 1. 查找需要更新的记录
    print("\n📊 扫描需要更新的记录:")
    total_updated = 0
    
    for old_key, new_key in key_mappings.items():
        records = cur.execute("""
            SELECT id, text, value
            FROM memories
            WHERE mtype = 'fact' AND key = ?
        """, (old_key,)).fetchall()
        
        if records:
            print(f"\n  {old_key}:")
            for rec_id, text, value in records:
                print(f"    ID={rec_id}, value='{value}', text='{text[:40]}...'")
                
                # 检查新 key 是否已存在
                existing = cur.execute("""
                    SELECT id FROM memories
                    WHERE mtype = 'fact' AND key = ?
                """, (new_key,)).fetchone()
                
                if existing:
                    # 新 key 已存在，删除旧记录
                    print(f"    → 删除（新 key '{new_key}' 已存在）")
                    cur.execute("DELETE FROM memories WHERE id = ?", (rec_id,))
                else:
                    # 更新 key 名称
                    print(f"    → 更新为 '{new_key}'")
                    cur.execute("""
                        UPDATE memories
                        SET key = ?
                        WHERE id = ?
                    """, (new_key, rec_id))
                
                total_updated += 1
    
    conn.commit()
    
    print_separator("标准化完成")
    print(f"\n✅ 已处理 {total_updated} 条记录")
    
    # 2. 显示最终状态
    print("\n📊 标准化后的 key 列表:")
    keys = cur.execute("""
        SELECT DISTINCT key, COUNT(*) as count
        FROM memories
        WHERE mtype = 'fact' AND key IS NOT NULL AND key != ''
        GROUP BY key
        ORDER BY key
    """).fetchall()
    
    for key, count in keys:
        status = "✅" if count == 1 else "⚠️"
        print(f"  {status} {key}: {count} 条记录")
    
    conn.close()

if __name__ == "__main__":
    try:
        standardize_keys()
    except Exception as e:
        print(f"\n❌ 标准化失败: {e}")
        import traceback
        traceback.print_exc()
