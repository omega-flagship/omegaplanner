import { useEffect, useState } from 'react'
import './task-boards.css'

export type Scope = 'mind' | 'swarm' | 'grand'
type Entity = { id: string; name: string }
type Goal = { id: string; title: string; status: string; assignee?: string | null; claimed_by?: string | null; parent_id?: string | null; result?: string | null }
type RequestRecord = { id: string; kind: string; state: string; from_goal: string; receiving_goal: string }
export type Board = { kind: Scope; entity_id: string | null; goals: Goal[]; requests: RequestRecord[] }
export type Matches = { candidates: { entity_id: string; name: string; active_claims: number; eligibility: string; capacity: string; cost: string; verified_capabilities: string[]; reasons: string[]; uncertainties: string[] }[] }
type Props = {
  minds: Entity[]; swarms: Entity[]
  loadBoard: (scope: Scope, entityId: string | undefined, signal: AbortSignal) => Promise<Board>
  loadMatches: (need: string, signal: AbortSignal) => Promise<Matches>
  openGoal: (id: string) => void
}
const columns = [
  { title: 'Ready', states: ['open'] },
  { title: 'In progress', states: ['claimed'] },
  { title: 'Waiting / blocked', states: ['waiting', 'stalled'] },
  { title: 'Finished', states: ['done', 'failed', 'cancelled'] },
]

export function TaskBoards({ minds, swarms, loadBoard, loadMatches, openGoal }: Props) {
  const [scope, setScope] = useState<Scope>('grand')
  const [entityId, setEntityId] = useState('')
  const [query, setQuery] = useState('')
  const [board, setBoard] = useState<Board | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [need, setNeed] = useState('plan')
  const [submittedNeed, setSubmittedNeed] = useState('')
  const [matchRefresh, setMatchRefresh] = useState(0)
  const [matches, setMatches] = useState<Matches | null>(null)
  const [matchError, setMatchError] = useState('')
  const entities = scope === 'mind' ? minds : swarms
  const selected = scope === 'grand' ? undefined : entityId || entities[0]?.id

  useEffect(() => {
    const controller = new AbortController()
    setBoard(null); setError('')
    if (scope !== 'grand' && !selected) {
      setError('No entities are available for this board.')
      return () => controller.abort()
    }
    loadBoard(scope, selected, controller.signal).then(value => {
      if (controller.signal.aborted) return
      if (value.kind !== scope || (scope !== 'grand' && value.entity_id !== selected)) {
        setError('The server returned a different board. Refresh to retry.'); return
      }
      setBoard(value)
    }).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Board unavailable.')
    })
    return () => controller.abort()
  }, [scope, selected, loadBoard, refresh])

  useEffect(() => {
    if (!submittedNeed) return
    const controller = new AbortController()
    setMatches(null); setMatchError('')
    loadMatches(submittedNeed, controller.signal).then(value => {
      if (!controller.signal.aborted) setMatches(value)
    }).catch(reason => {
      if (!controller.signal.aborted) setMatchError(reason instanceof Error ? reason.message : 'Matching unavailable.')
    })
    return () => controller.abort()
  }, [submittedNeed, loadMatches, matchRefresh])

  const goals = board?.goals.filter(g => `${g.title} ${g.id}`.toLowerCase().includes(query.toLowerCase())) ?? []
  const names = new Map(minds.map(m => [m.id, m.name]))
  return <main className="omega-task-boards">
    <header><h1>Work boards</h1><p>One shared work record across minds and swarms.</p></header>
    <div className="board-controls">
      <label>Board <select value={scope} onChange={e => { setScope(e.target.value as Scope); setEntityId('') }}>
        <option value="grand">Grand board</option><option value="swarm">Swarm board</option><option value="mind">Mind board</option>
      </select></label>
      {scope !== 'grand' && <label>{scope === 'mind' ? 'Mind' : 'Swarm'} <select value={selected ?? ''} onChange={e => setEntityId(e.target.value)}>{entities.map(e => <option key={e.id} value={e.id}>{e.name}</option>)}</select></label>}
      <label>Find work <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Title or task id" /></label>
      <button onClick={() => setRefresh(n => n + 1)}>Refresh</button>
    </div>
    {error ? <p role="alert">Board unavailable: {error}</p> : !board ? <p role="status">Loading board…</p> : <>
      <p aria-live="polite">{goals.length} of {board.goals.length} tasks shown · {board.requests.length} linked requests</p>
      <div className="board-columns">{columns.map(column => <section key={column.title} aria-label={column.title}>
        <h2>{column.title} <span>{goals.filter(g => column.states.includes(g.status)).length}</span></h2>
        {goals.filter(g => column.states.includes(g.status)).map(goal => <article key={goal.id}>
          <button className="task-title" onClick={() => openGoal(goal.id)}>{goal.title}</button>
          <p>{goal.status} · {names.get(goal.claimed_by || goal.assignee || '') || goal.claimed_by || goal.assignee || 'Unassigned'}</p>
          <small>{goal.id}</small>
          {goal.parent_id && <p>Parent: <button onClick={() => openGoal(goal.parent_id!)}>{goal.parent_id}</button></p>}
          {board.requests.filter(r => r.from_goal === goal.id || r.receiving_goal === goal.id).map(r => <p key={r.id}>{r.kind} request · {r.state} <small>{r.id}</small></p>)}
          {goal.result && <p>{goal.result}</p>}
        </article>)}
        {!goals.some(g => column.states.includes(g.status)) && <p>No tasks</p>}
      </section>)}</div>
      {goals.some(g => !columns.some(c => c.states.includes(g.status))) && <section aria-label="Other statuses"><h2>Other statuses</h2>{goals.filter(g => !columns.some(c => c.states.includes(g.status))).map(g => <article key={g.id}><button onClick={() => openGoal(g.id)}>{g.title}</button><p>{g.status}</p></article>)}</section>}
    </>}
    <section className="board-matching"><h2>Find a specialist swarm</h2>
      <form onSubmit={e => { e.preventDefault(); setSubmittedNeed(need.trim()); setMatchRefresh(n => n + 1) }}>
        <label>Service needed <input value={need} onChange={e => setNeed(e.target.value)} required maxLength={100} /></label>
        <button type="submit" disabled={!need.trim()}>Find matches</button>
      </form>
      <p>Recommendations show advertised services. Assignment and access require a separate accepted request.</p>
      {matchError && <p role="alert">Matching unavailable: {matchError}</p>}
      {submittedNeed && !matches && !matchError && <p role="status">Finding candidates…</p>}
      {matches?.candidates.map(c => <article key={c.entity_id}><h3>{c.name}</h3><p>{c.active_claims} active claims · Capacity: {c.capacity} · Cost: {c.cost}</p><p>Eligibility: {c.eligibility} · Verified capabilities: {c.verified_capabilities.join(', ') || 'None qualified'}</p><p>{c.reasons.join('; ')}</p><p>{c.uncertainties.join('; ')}</p></article>)}
      {matches && !matches.candidates.length && <p>No swarms advertise this service.</p>}
    </section>
  </main>
}
