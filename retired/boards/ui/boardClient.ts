import type { Board, Matches, Scope } from './TaskBoards'

/** Adapt the platform's authenticated read transport; keep session custody there.
 * The supplied transport must throw on non-2xx and honour AbortSignal.
 */
export type ReadTransport = <T>(path: string, options: { signal: AbortSignal }) => Promise<T>
export function boardClient(read: ReadTransport) {
  return {
    loadBoard(scope: Scope, entityId: string | undefined, signal: AbortSignal) {
      if (scope !== 'grand' && !entityId) return Promise.reject(new Error('Select a mind or swarm.'))
      const query = entityId ? '?entity_id=' + encodeURIComponent(entityId) : ''
      return read<Board>('/api/boards/' + scope + query, { signal })
    },
    loadMatches(need: string, signal: AbortSignal) {
      return read<Matches>('/api/match?need=' + encodeURIComponent(need), { signal })
    },
  }
}
