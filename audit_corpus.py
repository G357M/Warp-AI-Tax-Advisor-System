import os
import json
import csv
import psycopg2
from datetime import datetime
from collections import Counter, defaultdict
import math

# Configuration
DB_CONFIG = {
    'dbname': 'infohub_ai',
    'user': 'infohub_user',
    'password': 'xcX88l6XiMs-jDK',
    'host': 'localhost',
    'port': '5432'
}
CORPUS_BASE_DIR = '/root/infohub/corpus/live-newdocument/'
ARTIFACT_DIR = '/root/.openclaw/workspace/labs/warp-ai-tax-benchmark/audits/'

def get_raw_body_len(raw_json_path):
    try:
        with open(raw_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Try common content fields
            for field in ['additionalDescription', 'content', 'body', 'text', 'raw_text', 'description']:
                val = data.get(field)
                if val and isinstance(val, str):
                    return len(val)
            # Fallback: just count all string values
            total_len = 0
            def walk(obj):
                nonlocal total_len
                if isinstance(obj, str):
                    total_len += len(obj)
                elif isinstance(obj, dict):
                    for v in obj.values():
                        walk(v)
                elif isinstance(obj, list):
                    for item in obj:
                        walk(item)
            walk(data)
            return total_len
    except:
        return 0

def classify(norm_len, raw_body_len, norm_md_size, chunk_count, missing_files):
    if missing_files:
        return 'missing_layer'
    if norm_len == 0:
        if raw_body_len > 100:
            return 'suspicious_card'
        return 'unknown'
    
    # Check for shrinkage
    if raw_body_len > 0 and (norm_len / raw_body_len) < 0.4:
        return 'suspicious_shrink'
    
    if norm_len < 500:
        return 'healthy_short'
    elif norm_len < 5000:
        return 'healthy_medium'
    else:
        return 'healthy_large'

def run_audit():
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    print(f'Starting audit at {timestamp}')
    
    results = []
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        query = """
        SELECT 
            d.id, 
            d.title, 
            d.document_type, 
            d.category, 
            d.source_url, 
            d.full_text, 
            d.metadata,
            (SELECT COUNT(*) FROM document_chunks WHERE document_id = d.id) as chunk_count,
            (SELECT COUNT(*) FROM document_chunks WHERE document_id = d.id AND embedding IS NOT NULL) as embedded_chunk_count
        FROM documents d;
        """
        
        print('Fetching documents from database...')
        cur.execute(query)
        rows = cur.fetchall()
        total_docs = len(rows)
        print(f'Found {total_docs} documents.')

        for i, row in enumerate(rows):
            doc_id, title, doc_type, category, source_url, full_text, metadata, chunk_count, embedded_chunk_count = row
            
            if i % 100 == 0:
                print(f'Processing {i}/{total_docs}...')

            missing_files = []
            raw_json_size = 0
            raw_md_size = 0
            raw_body_len = 0
            norm_md_size = 0
            norm_text_len = 0
            db_full_text_len = len(full_text) if full_text else 0
            
            storage = metadata.get('storage', {})
            
            # 1. Raw JSON
            raw_json_rel = storage.get('raw_json')
            if raw_json_rel:
                path = os.path.join(CORPUS_BASE_DIR, raw_json_rel)
                if os.path.exists(path):
                    raw_json_size = os.path.getsize(path)
                    raw_body_len = get_raw_body_len(path)
                else:
                    missing_files.append('raw_json')
            else:
                missing_files.append('raw_json_path_missing')

            # 2. Raw MD
            raw_md_rel = storage.get('raw_md')
            if raw_md_rel:
                path = os.path.join(CORPUS_BASE_DIR, raw_md_rel)
                if os.path.exists(path):
                    raw_md_size = os.path.getsize(path)
                else:
                    missing_files.append('raw_md')
            else:
                missing_files.append('raw_md_path_missing')

            # 3. Normalized MD
            norm_md_rel = storage.get('normalized_md')
            if norm_md_rel:
                path = os.path.join(CORPUS_BASE_DIR, norm_md_rel)
                if os.path.exists(path):
                    norm_md_size = os.path.getsize(path)
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        norm_text_len = len(f.read())
                else:
                    missing_files.append('normalized_md')
            else:
                missing_files.append('normalized_md_path_missing')

            # Ratios
            ratio_norm_rawmd = norm_md_size / raw_md_size if raw_md_size > 0 else 0
            ratio_norm_rawbody = norm_text_len / raw_body_len if raw_body_len > 0 else 0
            ratio_db_norm = db_full_text_len / norm_text_len if norm_text_len > 0 else 0
            chunks_per_10k = (chunk_count / norm_text_len * 10000) if norm_text_len > 0 else 0

            label = classify(norm_text_len, raw_body_len, norm_md_size, chunk_count, missing_files)
            
            results.append({
                'corpus_name': 'live-newdocument',
                'uuid': doc_id,
                'title': title,
                'document_type': doc_type,
                'category': category or 'unknown',
                'source_url': source_url,
                'raw_json_size': raw_json_size,
                'raw_md_size': raw_md_size,
                'raw_body_proxy_len': raw_body_len,
                'normalized_md_size': norm_md_size,
                'normalized_text_len': norm_text_len,
                'db_full_text_len': db_full_text_len,
                'chunk_count': chunk_count,
                'embedded_chunk_count': embedded_chunk_count,
                'ratio_norm_rawmd': ratio_norm_rawmd,
                'ratio_norm_rawbody': ratio_norm_rawbody,
                'ratio_db_norm': ratio_db_norm,
                'chunks_per_10k_chars': chunks_per_10k,
                'classification': label,
                'notes': f'Missing: {', '.join(missing_files)}' if missing_files else ''
            })

        # Build Summary Tables
        summary = {}
        
        # 1. Counts by classification
        class_counts = Counter(r['classification'] for r in results)
        summary['counts_by_classification'] = dict(class_counts)
        
        # 2. Counts by type x classification
        type_class_counts = defaultdict(Counter)
        for r in results:
            type_class_counts[r['document_type']][r['classification']] += 1
        summary['counts_by_type_x_class'] = {k: dict(v) for k, v in type_class_counts.items()}

        # 3. Counts by category x classification
        cat_class_counts = defaultdict(Counter)
        for r in results:
            cat_class_counts[r['category']][r['classification']] += 1
        summary['counts_by_category_x_class'] = {k: dict(v) for k, v in cat_class_counts.items()}

        # 4. Distributions
        norm_lens = [r['normalized_text_len'] for r in results]
        db_lens = [r['db_full_text_len'] for r in results]
        chunk_counts = [r['chunk_count'] for r in results]
        
        def get_dist(data):
            if not data: return {}
            return {
                'min': min(data),
                'max': max(data),
                'avg': sum(data)/len(data),
                'median': sorted(data)[len(data)//2]
            }
        
        summary['distributions'] = {
            'normalized_text_len': get_dist(norm_lens),
            'db_full_text_len': get_dist(db_lens),
            'chunk_count': get_dist(chunk_counts)
        }

        # 5. Buckets
        buckets = defaultdict(int)
        for r in results:
            # Bucket by 1k char increments
            b = (r['normalized_text_len'] // 1000) * 1000
            buckets[f'{b}-{b+999}'] += 1
        summary['buckets_text_len'] = dict(sorted(buckets.items(), key=lambda x: int(x[0].split('-')[0])))

        # 6. Healthy vs Broken
        healthy_classes = [c for c in ['healthy_short', 'healthy_medium', 'healthy_large'] if class_counts[c] > 0]
        broken_classes = [c for c in ['suspicious_shrink', 'suspicious_card', 'missing_layer'] if class_counts[c] > 0]
        summary['top_healthy_classes'] = healthy_classes
        summary['top_broken_classes'] = broken_classes
        
        healthy_total = sum(class_counts[c] for c in healthy_classes)
        summary['health_estimate_fraction'] = healthy_total / total_docs if total_docs > 0 else 0

        # Save CSV
        csv_path = os.path.join(ARTIFACT_DIR, f'full_corpus_state_{timestamp}.csv')
        if results:
            keys = results[0].keys()
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                dict_writer = csv.DictWriter(f, fieldnames=keys)
                dict_writer.writeheader()
                dict_writer.writerows(results)
        
        # Save JSON
        json_path = os.path.join(ARTIFACT_DIR, f'full_corpus_state_{timestamp}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
            
        # Save MD Report
        md_path = os.path.join(ARTIFACT_DIR, f'full_corpus_state_{timestamp}.md')
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f'# Full Corpus State Audit - {timestamp}\n\n')
            f.write(f'**Total Documents Processed:** {total_docs}\n\n')
            
            f.write('## Summary Counts\n\n')
            f.write('| Classification | Count |\n|---|---|\n')
            for c, count in class_counts.items():
                f.write(f'| {c} | {count} |\n')
            
            f.write('\n## Health Estimate\n\n')
            h_frac = summary['health_estimate_fraction']
            f.write(f'Estimated Healthy Fraction: {h_frac:.2%}\n\n')
            
            f.write('## Distributions\n\n')
            for d_name, vals in summary['distributions'].items():
                f.write(f'### {d_name}\n')
                f.write(f'- Min: {vals['min']}\n- Max: {vals['max']}\n- Avg: {vals['avg']:.2f}\n- Median: {vals['median']}\n\n')

            f.write('## Top Broken Classes\n\n')
            for c in summary['top_broken_classes']:
                f.write(f'- {c}: {class_counts[c]} docs\n')

        print(f'Audit complete.')
        print(f'CSV: {csv_path}')
        print(f'JSON: {json_path}')
        print(f'MD: {md_path}')
        
        cur.close()
        conn.close()
        
        return csv_path, json_path, md_path

    except Exception as e:
        print(f'CRITICAL ERROR during audit: {e}')
        import traceback
        traceback.print_exc()
        return None, None, None

if __name__ == '__main__':
    run_audit()
