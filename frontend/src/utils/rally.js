// Decorative rally for one simulated point. The WINNER of the point comes from the point model (utils/tennisSim.js);
// the rally (how many shots, ace/winner/error, where the ball lands) is drawn only to be watched: it adds no information.
export const COURT = { left: 50, right: 750, top: 60, bottom: 360, net: 400, midY: 210, sTop: 97, sBot: 323 }

const rnd = (rng, a, b) => a + (b - a) * rng()

export function makeRally(r, parity, rng = Math.random) {
  const { server, winner } = r
  let n = 1
  if (rng() > 0.1) {
    n = 2
    while (rng() < 0.78 && n < 20) n++
  }
  const last = n % 2 === 1 ? server : 1 - server
  let kind
  if (n === 1) kind = winner === server ? 'ace' : 'doublefault'
  else kind = last === winner ? 'winner' : 'error'
  const shots = []
  for (let k = 1; k <= n; k++) {
    const hitter = k % 2 === 1 ? server : 1 - server
    const dir = hitter === 0 ? 1 : -1 // direction the ball travels (left player hits to the right)
    const isLast = k === n
    let type = 'in'
    let to
    if (k === 1) {
      // serve from the deuce (even) or ad (odd) court, diagonal into the opposite service box
      const fromBottom = (parity % 2 === 0) === (hitter === 0)
      const yTo = fromBottom ? rnd(rng, COURT.sTop + 8, COURT.midY - 8) : rnd(rng, COURT.midY + 8, COURT.sBot - 8)
      to = { x: COURT.net + dir * rnd(rng, 90, 180), y: yTo }
      if (isLast && kind === 'ace') to = { x: COURT.net + dir * rnd(rng, 150, 185), y: fromBottom ? COURT.sTop + 10 : COURT.sBot - 10 }
      if (isLast && kind === 'doublefault') {
        type = 'net'
        to = { x: COURT.net, y: yTo }
      }
      shots.push({ hitter, type, to, serve: true, fromBottom })
      continue
    }
    to = { x: COURT.net + dir * rnd(rng, 150, 325), y: rnd(rng, COURT.sTop + 10, COURT.sBot - 10) }
    if (isLast && kind === 'winner') to = { x: COURT.net + dir * rnd(rng, 230, 335), y: rng() < 0.5 ? COURT.sTop + 6 : COURT.sBot - 6 }
    if (isLast && kind === 'error') {
      const q = rng()
      if (q < 0.4) {
        type = 'net'
        to = { x: COURT.net, y: rnd(rng, 150, 270) }
      } else if (q < 0.75) {
        type = 'long'
        to = { x: COURT.net + dir * rnd(rng, 360, 395), y: to.y }
      } else {
        type = 'wide'
        to = { x: to.x, y: rng() < 0.5 ? COURT.sTop - rnd(rng, 14, 30) : COURT.sBot + rnd(rng, 14, 30) }
      }
    }
    shots.push({ hitter, type, to })
  }
  return { server, winner, kind, n, shots, parity }
}

export const KIND_TEXT = { ace: 'ACE', doublefault: 'DOBLE FALTA', winner: 'WINNER', error: 'ERROR' }
