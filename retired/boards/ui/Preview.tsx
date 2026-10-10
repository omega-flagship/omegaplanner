import { useCallback, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { TaskBoards, type Board, type Scope } from './TaskBoards'

const minds = [{ id: 'm-planner', name: 'Planner' }, { id: 'm-reviewer', name: 'Reviewer' }]
const swarms = [{ id: 's-plan', name: 'Planning swarm' }, { id: 's-review', name: 'Review swarm' }]
const goals = [
  { id: 'g-ready', title: 'Prepare an invented workshop plan', status: 'open', assignee: 'm-planner', swarm: 's-plan' },
  { id: 'g-review', title: 'Review room availability assumptions', status: 'claimed', claimed_by: 'm-reviewer', parent_id: 'g-ready', swarm: 's-review' },
  { id: 'g-blocked', title: 'Confirm synthetic room booking', status: 'stalled', assignee: 'm-planner', swarm: 's-plan' },
  { id: 'g-done', title: 'Record invented budget constraints', status: 'done', assignee: 'm-planner', result: 'Synthetic constraints recorded; completion evidence not independently verified.', swarm: 's-plan' },
]
function Preview() {
  const [mode, setMode] = useState('normal')
  const [opened, setOpened] = useState('')
  const loadBoard = useCallback(async (scope: Scope, id: string | undefined): Promise<Board> => {
    if (mode === 'error') throw new Error('Synthetic API unavailable')
    return { kind: scope, entity_id: id ?? null, goals: mode === 'empty' ? [] : goals.filter(g => scope === 'grand' || (scope === 'swarm' ? g.swarm === id : (g.assignee || g.claimed_by) === id)), requests: mode === 'empty' ? [] : [{ id: 'rq-review', kind: 'review', state: 'working', from_goal: 'g-ready', receiving_goal: 'g-review' }] }
  }, [mode])
  const loadMatches = useCallback(async () => {
    if (mode === 'error') throw new Error('Synthetic matching unavailable')
    return { candidates: mode === 'empty' ? [] : [{ entity_id: 's-plan', name: 'Planning swarm', active_claims: 1, capacity: 'unknown', cost: 'unknown', eligibility: 'unverified', verified_capabilities: [], reasons: ['Advertises planning service'], uncertainties: ['Synthetic preview; no demonstrated capability qualification'] }] }
  }, [mode])
  return <><aside style={{ padding: 16, background: '#e7edf5' }}><strong>Synthetic UI preview — no live tasks or minds</strong> <label>Scenario <select value={mode} onChange={e => setMode(e.target.value)}><option value="normal">Populated</option><option value="empty">Empty</option><option value="error">API error</option></select></label>{opened && <p role="status">Opened synthetic task: {opened}</p>}</aside><TaskBoards minds={minds} swarms={swarms} loadBoard={loadBoard} loadMatches={loadMatches} openGoal={setOpened} /></>
}
createRoot(document.getElementById('root')!).render(<Preview />)
