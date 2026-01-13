"""
清理数据库中重复的 fact 记录
"""
import sqlite3

def print_separator(title=""):
    if title:
        print(f"\n{'='*70}")
        print(f"  {title}")
        print('='*70)
    else:
        print('='*70)

def clean_duplicate_facts():
    """清理数据库中重复的 fact 记录，每个 key 只保留最新的"""
    print_separator("🧹 清理重复的 fact 记录")
    
    db_path = "memory.sqlite"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 1. 查找所有 fact 类型的记录
    print("\n📊 当前数据库状态:")
    facts = cur.execute("""
        SELECT id, text, key, value, created_at
        FROM memories
        WHERE mtype = 'fact' AND key IS NOT NULL AND key != ''
        ORDER BY key, created_at DESC
    """).fetchall()
    
    if not facts:
        print("  ℹ️ 数据库中没有 fact 记录")
        conn.close()
        return
    
    print(f"  总计 {len(facts)} 条 fact 记录")
    
    # 2. 按 key 分组
    key_groups = {}
    for fact in facts:
        fact_id, text, key, value, created_at = fact
        if key not in key_groups:
            key_groups[key] = []
        key_groups[key].append(fact)
    
    # 3. 显示重复情况
    print("\n📋 按 key 分组:")
    duplicates_found = False
    for key, records in sorted(key_groups.items()):
        if len(records) > 1:
            duplicates_found = True
            print(f"\n  ❌ {key}: {len(records)} 条记录（有重复）")
            for rec in records:
                print(f"     ID={rec[0]}, value='{rec[3]}', text='{rec[1][:40]}...', time={rec[4]}")
        else:
            print(f"  ✅ {key}: 1 条记录")
    
    if not duplicates_found:
        print("\n✅ 没有重复的 fact 记录，数据库状态良好")
        conn.close()
        return
    
    # 4. 清理重复记录
    print_separator("开始清理")
    
    deleted_count = 0
    for key, records in key_groups.items():
        if len(records) > 1:
            # 保留最新的（created_at 最大的），删除其他的
            records_sorted = sorted(records, key=lambda x: x[4], reverse=True)
            keep_record = records_sorted[0]
            delete_records = records_sorted[1:]
            
            print(f"\n🔄 {key}:")
            print(f"  ✓ 保留: ID={keep_record[0]}, value='{keep_record[3]}', time={keep_record[4]}")
            
            for rec in delete_records:
                print(f"  ✗ 删除: ID={rec[0]}, value='{rec[3]}', time={rec[4]}")
                cur.execute("DELETE FROM memories WHERE id = ?", (rec[0],))
                deleted_count += 1
    
    conn.commit()
    
    print_separator("清理完成")
    print(f"\n✅ 已删除 {deleted_count} 条重复记录")
    
    # 5. 验证结果
    print("\n📊 清理后的数据库状态:")
    facts_after = cur.execute("""
        SELECT key, COUNT(*) as count
        FROM memories
        WHERE mtype = 'fact' AND key IS NOT NULL AND key != ''
        GROUP BY key
    """).fetchall()
    
    for key, count in facts_after:
        status = "✅" if count == 1 else "❌"
        print(f"  {status} {key}: {count} 条记录")
    
    conn.close()

if __name__ == "__main__":
    try:
        clean_duplicate_facts()
    except Exception as e:
        print(f"\n❌ 清理失败: {e}")
        import traceback
        traceback.print_exc()
