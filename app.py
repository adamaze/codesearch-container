from flask import Flask, render_template_string, request, jsonify
import subprocess
import re
import os

app = Flask(__name__)

# Configuration
REPOS_PATH = "/repos"
EXCLUDE_DIRS = {".git", "elastiflow"}
EXCLUDE_FILES = {"jquery.min.js", "jquery.dataTables.min.js", "jquery.dataTables.min.css"}

def chained_grep(text, patterns):
    """Apply multiple grep patterns in sequence (case-insensitive)"""
    lines = text.split('\n')
    for pattern in patterns:
        if not pattern:
            continue
        lines = [line for line in lines if re.search(pattern, line, re.IGNORECASE)]
    return '\n'.join(lines)

def search_code(query, *additional_patterns):
    """Search through repos using grep and filename search"""
    if not query:
        return []
    
    results = []
    exclude_dir_args = ",".join(EXCLUDE_DIRS)
    exclude_file_args = ",".join(EXCLUDE_FILES)
    
    try:
        # Content search
        cmd = [
            "grep",
            f"--exclude-dir={exclude_dir_args}",
            "-i",
            f"--exclude={exclude_file_args}",
            "-r",
            "-n",
            query,
            REPOS_PATH
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        grep_output = result.stdout
        
        # Apply additional patterns (chained grep)
        if additional_patterns:
            grep_output = chained_grep(grep_output, additional_patterns)
        
        if grep_output:
            results.extend(grep_output.strip().split('\n'))
        
        # Filename search
        find_cmd = f"find {REPOS_PATH} -iname '*{query}*'"
        find_result = subprocess.run(find_cmd, shell=True, capture_output=True, text=True, timeout=30)
        filename_matches = find_result.stdout
        
        if filename_matches:
            filename_lines = filename_matches.strip().split('\n')
            if additional_patterns:
                filename_output = '\n'.join([f"[FILENAME] {line}" for line in filename_lines])
                filename_output = chained_grep(filename_output, additional_patterns)
                results.extend(filename_output.strip().split('\n'))
            else:
                results.extend([f"[FILENAME] {line}" for line in filename_lines])
    
    except subprocess.TimeoutExpired:
        return ["Error: Search timed out"]
    except Exception as e:
        return [f"Error: {str(e)}"]
    
    return [r for r in results if r]  # Remove empty lines

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeSearch</title>
    <link
        rel="search"           
        type="application/opensearchdescription+xml"
        title="[CodeSearch]"
        href="/opensearch.xml" />
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: #0d1117;
            color: #c9d1d9;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            margin-bottom: 30px;
            font-size: 28px;
            color: #58a6ff;
        }
        .search-section {
            margin-bottom: 30px;
        }
        .search-input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
        }
        input, button {
            padding: 10px 15px;
            border: 1px solid #30363d;
            border-radius: 6px;
            background: #161b22;
            color: #c9d1d9;
            font-family: monospace;
            font-size: 14px;
        }
        input {
            flex: 1;
        }
        button {
            background: #238636;
            color: white;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.2s;
        }
        button:hover {
            background: #2ea043;
        }
        button:active {
            background: #1f6feb;
        }
        .additional-patterns {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
        }
        .pattern-tag {
            display: flex;
            align-items: center;
            gap: 6px;
            background: #1f6feb;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
        }
        .pattern-tag button {
            background: none;
            border: none;
            color: #c9d1d9;
            cursor: pointer;
            padding: 0;
            font-size: 16px;
        }
        .results {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 0;
            max-height: 600px;
            overflow-y: auto;
        }
        .result-item {
            padding: 12px 15px;
            border-bottom: 1px solid #30363d;
            font-size: 12px;
            font-family: monospace;
            word-break: break-all;
            cursor: pointer;
            transition: background 0.2s;
        }
        .result-item[data-file] {
            cursor: pointer;
        }
        .result-item[data-file]:hover {
            text-decoration: underline;
        }
        .result-item:hover {
            background: #0d1117;
        }
        .result-item:last-child {
            border-bottom: none;
        }
        .result-item.filename {
            color: #79c0ff;
            font-weight: 600;
        }
        .status {
            margin-top: 15px;
            font-size: 13px;
            color: #8b949e;
        }
        .error {
            color: #f85149;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 CodeSearch</h1>
        
        <div class="search-section">
            <div class="search-input-group">
                <input type="text" id="mainQuery" placeholder='Search terms (e.g., "tmux alias" or tmux "a lias")...' autocomplete="off" value="{{ initial_query }}">
                <button onclick="search()">Search</button>
            </div>
        </div>
        
        <div id="results" class="results" style="display: none;"></div>
        <div id="status" class="status"></div>
    </div>

    <script>
        function extractFilePath(line) {
            if (line.startsWith('[FILENAME]')) {
                return line.replace('[FILENAME] ', '').trim();
            }
            // Format: /path/to/file:line_number:content
            const match = line.match(/^(.+?):(\d+):/);
            return match ? match[1] : null;
        }
        
        function openFile(element) {
            const filePath = element.dataset.file;
            if (filePath) {
                fetch('/api/file', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: filePath })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const newWindow = window.open();
                        newWindow.document.write(`<pre style="background: #0d1117; color: #c9d1d9; padding: 20px; font-family: monospace; font-size: 13px; line-height: 1.5; margin: 0; white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(data.content)}</pre>`);
                        newWindow.document.title = filePath;
                    }
                })
                .catch(e => alert('Error loading file: ' + e));
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function parseFilters(input) {
            const filters = [];
            let current = '';
            let inQuotes = false;
            
            for (let i = 0; i < input.length; i++) {
                const char = input[i];
                if (char === '"') {
                    inQuotes = !inQuotes;
                } else if (char === ' ' && !inQuotes) {
                    if (current.trim()) filters.push(current.trim());
                    current = '';
                } else {
                    current += char;
                }
            }
            if (current.trim()) filters.push(current.trim());
            return filters;
        }
        
        function search() {
            const input = document.getElementById('mainQuery').value.trim();
            if (!input) {
                document.getElementById('status').innerHTML = '<span class="error">Enter search terms</span>';
                return;
            }
            
            const filters = parseFilters(input);
            const query = filters[0];
            const patterns = filters.slice(1);
            
            document.getElementById('status').innerHTML = 'Searching...';
            document.getElementById('results').style.display = 'none';
            
            fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, patterns })
            })
            .then(r => r.json())
            .then(data => {
                const resultsDiv = document.getElementById('results');
                const statusDiv = document.getElementById('status');
                
                if (data.results.length === 0) {
                    statusDiv.innerHTML = 'No results found';
                    resultsDiv.style.display = 'none';
                } else {
                    resultsDiv.innerHTML = data.results
                        .map(r => {
                            const isFilename = r.startsWith('[FILENAME]');
                            const filePath = extractFilePath(r);
                            const clickable = filePath ? `data-file="${filePath}" onclick="openFile(this)"` : '';
                            return `<div class="result-item ${isFilename ? 'filename' : ''}" ${clickable}>${r}</div>`;
                        })
                        .join('');
                    resultsDiv.style.display = 'block';
                    statusDiv.innerHTML = `Found ${data.results.length} result${data.results.length !== 1 ? 's' : ''}`;
                }
            })
            .catch(e => {
                document.getElementById('status').innerHTML = `<span class="error">Error: ${e}</span>`;
            });
        }
        
        document.getElementById('mainQuery').addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                e.preventDefault();
                search();
            }
        });
        
        // Auto-search if query parameter was provided
        if ('{{ initial_query }}' && '{{ initial_query }}'.trim()) {
            search();
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    query = request.args.get('q', '')
    html = render_template_string(HTML_TEMPLATE, initial_query=query)
    return html

@app.route('/opensearch.xml')
def opensearch():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>CodeSearch</ShortName>
  <Description>Search through code repositories</Description>
  <Url type="text/html" template="http://localhost:5000/?q={searchTerms}"/>
  <LongName>CodeSearch - Multi-Repo Code Search</LongName>
  <Url type="application/x-suggestions+json" template="http://localhost:5000/api/suggestions?q={searchTerms}"/>
  <Contact>admin@codesearch.local</Contact>
  <Tags>code search repositories</Tags>
  </OpenSearchDescription>'''

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.json
    query = data.get('query', '')
    patterns = data.get('patterns', [])
    
    results = search_code(query, *patterns)
    return jsonify({'results': results})

@app.route('/api/file', methods=['POST'])
def api_file():
    data = request.json
    filepath = data.get('path', '')
    
    # Security: ensure path is within REPOS_PATH
    if not os.path.abspath(filepath).startswith(os.path.abspath(REPOS_PATH)):
        return jsonify({'success': False, 'error': 'Invalid path'})
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return jsonify({'success': True, 'content': content})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/suggestions', methods=['GET'])
def api_suggestions():
    """OpenSearch suggestions endpoint"""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify(['', []])
    
    # Return basic suggestions based on search term
    suggestions = [q]
    return jsonify([q, suggestions])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
