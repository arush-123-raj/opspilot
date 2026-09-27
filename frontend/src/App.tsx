import { useState } from 'react'

function App() {
  const [status] = useState('Online')

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>OpsPilot</h1>
      <p>AI-Powered Incident Management & Observability Platform</p>
      <div>
        <strong>System Status: </strong>
        <span style={{ color: 'green' }}>{status}</span>
      </div>
    </div>
  )
}

export default App
