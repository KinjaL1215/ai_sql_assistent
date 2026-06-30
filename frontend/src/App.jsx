import { useEffect, useState } from 'react'
import './App.css'

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

  useEffect(() => {
    document.documentElement.classList.add('dark')
  }, [])

  const handleUpload = async (event) => {
    event.preventDefault()
    if (!uploadFile) {
      setError('Please select a CSV or Excel file before uploading.')
      return
    }

    setError('')
    setMessage('')
    setUploadStatus('Preparing your dataset...')

    const formData = new FormData()
    formData.append('file', uploadFile)

    try {
      const response = await fetch('http://127.0.0.1:8000/upload', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      if (!response.ok) {
        throw new Error(data.detail || 'The file could not be uploaded.')
      }

      setUploadStatus('Dataset uploaded successfully.')
      setMessage(`Table "${data.table_name}" is ready with ${data.rows} rows.`)
      setTableName(data.table_name)
    } catch (err) {
      setUploadStatus('Upload was not completed.')
      setError(err.message)
    }
  }

  const handleAsk = async (event) => {
    event.preventDefault()
    if (!prompt.trim()) {
      setError('Please enter a business question before running the query.')
      return
    }

    setError('')
    setMessage('')
    setLoading(true)

    try {
      const query = new URLSearchParams({ prompt, table_name: tableName })
      const response = await fetch(`http://127.0.0.1:8000/ask?${query.toString()}`, {
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

  const renderTable = () => {
    if (!rows.length) {
      return <p className="empty">Run a question to preview matching records.</p>
    }

    const columns = Object.keys(rows[0])
    return (
      <div className="table-wrapper">
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
      <header className="hero">
        <nav className="topbar" aria-label="Application controls">
          <div className="brand-mark">SQL</div>
          <span>AI SQL Assistant</span>
          <button className="theme-toggle" onClick={() => document.documentElement.classList.toggle('dark')}>
            Toggle theme
          </button>
        </nav>

        <div className="hero-content">
          <p className="eyebrow">Private data analysis workspace</p>
          <h1>Turn spreadsheets into reliable SQL insights.</h1>
          <p className="subtitle">
            Upload a dataset, ask a plain-English question, and review the generated SQL with the returned records in one focused workflow.
          </p>
          <div className="hero-actions">
            <a href="#ask" className="primary-link">Ask a question</a>
            <a href="#upload" className="secondary-link">Upload dataset</a>
          </div>
        </div>

        <div className="hero-panel" aria-label="Workflow summary">
          <div>
            <span className="metric">01</span>
            <p>Import CSV or Excel files into PostgreSQL.</p>
          </div>
          <div>
            <span className="metric">02</span>
            <p>Generate SQL from natural language prompts.</p>
          </div>
          <div>
            <span className="metric">03</span>
            <p>Validate answers with a structured result preview.</p>
          </div>
        </div>
      </header>

      <main>
        <section className="workspace-card" id="upload">
          <div className="section-heading">
            <p className="eyebrow">Step 1</p>
            <h2>Upload a dataset</h2>
            <p>Choose a CSV or Excel file and create a query-ready PostgreSQL table.</p>
          </div>
          <form onSubmit={handleUpload} className="form-grid">
            <label>
              Dataset file
              <input
                type="file"
                accept=".csv,.xls,.xlsx"
                onChange={(event) => setUploadFile(event.target.files?.[0] || null)}
              />
            </label>
            <button type="submit" className="primary">
              Upload dataset
            </button>
          </form>
          <p className="meta">Active table: <strong>{tableName}</strong></p>
          <p className="status">{uploadStatus}</p>
        </section>

        <section className="workspace-card" id="ask">
          <div className="section-heading">
            <p className="eyebrow">Step 2</p>
            <h2>Ask a business question</h2>
            <p>Describe the answer you need. The assistant will generate SQL and return matching records.</p>
          </div>
          <form onSubmit={handleAsk} className="form-grid">
            <label>
              Table name
              <input
                type="text"
                value={tableName}
                onChange={(event) => setTableName(event.target.value)}
                placeholder="heart"
              />
            </label>
            <label className="full-width">
              Question
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder="Show the average cholesterol level for patients older than 60."
                rows={4}
              />
            </label>
            <button type="submit" className="primary" disabled={loading}>
              {loading ? 'Analyzing dataset...' : 'Generate SQL'}
            </button>
          </form>

          {error && <div className="alert error">{error}</div>}
          {message && <div className="alert success">{message}</div>}

          {sql && (
            <div className="sql-card">
              <h3>Generated SQL</h3>
              <pre>{sql}</pre>
            </div>
          )}

          <div className="results">
            <h3>Result preview</h3>
            {renderTable()}
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
