import { useEffect, useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

const EXAMPLE_PROMPTS = [
  { label: 'Avg Cholesterol > 60', prompt: 'Show the average cholesterol level for patients older than 60.' },
  { label: 'Count by Chest Pain', prompt: 'Count how many rows grouped by chest pain type (cp).' },
  { label: 'Highest Max HR', prompt: 'Show the top 10 records sorted by maximum heart rate (thalach) descending.' },
  { label: 'High Blood Pressure', prompt: 'Show all patients with resting blood pressure (trestbps) greater than 140.' },
];

function App() {
  const [prompt, setPrompt] = useState('')
  const [tableName, setTableName] = useState('heart')
  const [uploadFile, setUploadFile] = useState(null)
  const [uploadStatus, setUploadStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const [sql, setSql] = useState('')
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [columnsList, setColumnsList] = useState([])
  const [copied, setCopied] = useState(false)
  const [isDark, setIsDark] = useState(true)

  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])

  const toggleTheme = () => {
    document.documentElement.classList.toggle('dark')
    setIsDark((value) => !value)
  }

  const fetchSchema = async (table) => {
    if (!table) return
    try {
      const response = await fetch(`${API_BASE_URL}/schema/${table}`)
      if (response.ok) {
        const data = await response.json()
        setColumnsList(data.columns || [])
      }
    } catch (err) {
      console.error('Failed to fetch schema:', err)
    }
  }

  useEffect(() => {
    fetchSchema(tableName)
  }, [tableName])

  const handleUpload = async (event) => {
    event.preventDefault()
    if (!uploadFile) {
      setError('Please select a CSV or Excel file before uploading.')
      return
    }

    setError('')
    setMessage('')
    setUploadStatus('Preparing dataset...')

    const formData = new FormData()
    formData.append('file', uploadFile)

    try {
      const response = await fetch(`${API_BASE_URL}/upload`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'The file could not be uploaded.')
      }

      setUploadStatus('Uploaded successfully.')
      setMessage(`Table "${data.table_name}" is ready with ${data.rows} rows.`)
      setTableName(data.table_name)
      fetchSchema(data.table_name)
    } catch (err) {
      setUploadStatus('Upload failed.')
      setError(err.message)
    }
  }

  const handleAsk = async (event) => {
    if (event) event.preventDefault()
    if (!prompt.trim()) {
      setError('Please enter a business question before running the query.')
      return
    }

    setError('')
    setMessage('')
    setLoading(true)

    try {
      const query = new URLSearchParams({ prompt, table_name: tableName })
      const response = await fetch(`${API_BASE_URL}/ask?${query.toString()}`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'The query could not be completed.')
      }

      setSql(data.sql || '')
      setRows(data.rows || [])
      if (data.row_count !== undefined) {
        setMessage(`${data.row_count} result row${data.row_count === 1 ? '' : 's'} returned.`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleCopySql = () => {
    if (sql) {
      navigator.clipboard.writeText(sql)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadCSV = () => {
    if (!rows.length) return
    const headers = Object.keys(rows[0])
    const csvRows = [
      headers.join(','),
      ...rows.map(row => headers.map(header => {
        const val = row[header] === null || row[header] === undefined ? '' : String(row[header])
        const escaped = val.replace(/"/g, '""')
        return `"${escaped}"`
      }).join(','))
    ]
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${tableName}_results.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const renderTable = () => {
    if (!rows.length) {
      return (
        <div className="empty-state animate-fade-in">
          <div className="empty-state-icon">
            <svg width="40" height="40" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.21 3.58 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.58 4 8 4s8-1.79 8-4M4 7c0-2.21 3.58-4 8-4s8 1.79 8 4m0 5c0 2.21-3.58 4-8 4s-8-1.79-8-4" />
            </svg>
          </div>
          <p className="empty-state-title">No Data Loaded</p>
          <p className="empty-state-desc">Select or type an ask query above to query the active database.</p>
        </div>
      )
    }

    const columns = Object.keys(rows[0])
    return (
      <div className="table-wrapper animate-fade-in">
        <table>
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((col) => (
                  <td key={col}>{String(row[col])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <nav className="topbar" aria-label="Application controls">
        <div className="brand-wrapper">
          <div className="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M4 7V4h16v3M9 20h6M12 7v13" />
            </svg>
          </div>
          <div className="brand-copy">
            <span className="brand-title">QueryPilot</span>
            <span className="brand-subtitle">AI data workspace</span>
          </div>
          <span className="badge-pill"><span className="status-dot" />System online</span>
        </div>
        <button className="theme-toggle" onClick={toggleTheme} title="Toggle color theme" aria-label="Toggle color theme">
          {isDark ? '☀' : '☾'}
        </button>
      </nav>

      <div className="dashboard-grid">
        <aside className="sidebar">
          <div className="workspace-label"><span />WORKSPACE</div>
          <div className="panel-section">
            <div className="section-heading"><h3 className="section-title">Upload dataset</h3><span>01</span></div>
            <form onSubmit={handleUpload} className="upload-form">
              <div className="file-input-wrapper">
                <input
                  type="file"
                  id="file-upload"
                  accept=".csv,.xls,.xlsx"
                  onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
                />
                <label htmlFor="file-upload" className="file-dropzone">
                  <svg width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  <strong>{uploadFile ? uploadFile.name : 'Drop your data here'}</strong>
                  <span>{uploadFile ? 'Ready to upload' : 'CSV or Excel · Max 50 MB'}</span>
                </label>
              </div>
              <button type="submit" className="btn btn-secondary w-full">
                Upload Table
              </button>
            </form>
            {uploadStatus && <div className="status-badge animate-fade-in">{uploadStatus}</div>}
          </div>

          <div className="panel-section">
            <div className="section-heading"><h3 className="section-title">Active dataset</h3><span>02</span></div>
            <div className="table-status-info">
              <div className="info-row">
                <span className="info-label">Table Name:</span>
                <input
                  type="text"
                  className="table-input"
                  value={tableName}
                  onChange={(event) => setTableName(event.target.value)}
                  placeholder="heart"
                />
              </div>
              {columnsList.length > 0 && (
                <div className="schema-view">
                  <span className="info-label">Columns ({columnsList.length}):</span>
                  <div className="schema-tags">
                    {columnsList.map((col) => (
                      <span key={col} className="schema-tag" title={col}>
                        {col}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="sidebar-footnote">
            <span className="privacy-icon">✦</span>
            <p>Queries are generated from your active table schema.</p>
          </div>
        </aside>

        <main className="main-workspace">
          <section className="workspace-panel prompt-panel">
            <div className="eyebrow">NATURAL LANGUAGE TO SQL</div>
            <div className="prompt-heading">
              <div>
                <h1>What would you like to explore?</h1>
                <p>Describe the insight you need. We’ll write and run the SQL for you.</p>
              </div>
              <div className="dataset-indicator"><span className="database-glyph">⌁</span>{tableName || 'No table selected'}</div>
            </div>
            <form onSubmit={handleAsk} className="ask-form">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                    handleAsk(event)
                  }
                }}
                placeholder="e.g., Show the average cholesterol level for patients older than 60."
                rows={3}
              />
              <div className="example-prompts-wrapper">
                <span className="example-label">Examples:</span>
                <div className="example-chips">
                  {EXAMPLE_PROMPTS.map((ex) => (
                    <button
                      key={ex.label}
                      type="button"
                      className="chip-btn"
                      onClick={() => setPrompt(ex.prompt)}
                    >
                      {ex.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="ask-actions">
                <span className="keyboard-tip">Press <kbd>Ctrl</kbd> <kbd>Enter</kbd> to run</span>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? (
                    <>
                      <svg className="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <circle cx="12" cy="12" r="10" strokeDasharray="30 30" />
                      </svg>
                      Analyzing Dataset...
                    </>
                  ) : <>Generate query <span className="button-arrow">→</span></>}
                </button>
              </div>
            </form>
          </section>

          {error && <div className="toast toast-error animate-fade-in">{error}</div>}
          {message && <div className="toast toast-success animate-fade-in">{message}</div>}

          {sql && (
            <section className="workspace-panel sql-panel animate-fade-in">
              <div className="panel-header">
                <div><div className="panel-kicker">QUERY OUTPUT</div><h3 className="panel-title">Generated SQL</h3></div>
                <button className="btn btn-icon" onClick={handleCopySql} title="Copy to clipboard">
                  {copied ? (
                    <>
                      <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" className="text-green">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Copied!
                    </>
                  ) : (
                    <>
                      <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                      </svg>
                      Copy SQL
                    </>
                  )}
                </button>
              </div>
              <div className="code-block-wrapper">
                <pre><code>{sql}</code></pre>
              </div>
            </section>
          )}

          <section className="workspace-panel results-panel">
            <div className="panel-header">
              <div><div className="panel-kicker">DATA PREVIEW</div><h3 className="panel-title">Results {rows.length > 0 && <span className="result-count">{rows.length} rows</span>}</h3></div>
              {rows.length > 0 && (
                <button className="btn btn-icon" onClick={handleDownloadCSV} title="Download CSV">
                  <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Export CSV
                </button>
              )}
            </div>
            {renderTable()}
          </section>
        </main>
      </div>
    </div>
  )
}

export default App
