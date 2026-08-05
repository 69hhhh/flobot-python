import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let vite
let directConnection

before(async () => {
  vite = await createServer({
    root: fileURLToPath(new URL('..', import.meta.url)),
    appType: 'custom',
    logLevel: 'silent',
    server: { middlewareMode: true },
  })
  directConnection = await vite.ssrLoadModule('/src/data/directConnection.ts')
})

after(async () => {
  await vite?.close()
})

test('official room URL is accepted for the local Flobot service', () => {
  const parsed = directConnection.parseDirectConnection({
    roomUrl: 'https://generals.io/games/my-private-room',
    userId: 'private-user-id',
  })
  assert.equal(parsed.roomId, 'my-private-room')
  assert.equal(parsed.userId, 'private-user-id')
})

test('non-official URL is rejected before user_id can be sent', () => {
  assert.throws(() => directConnection.parseDirectConnection({
    roomUrl: 'https://example.com/games/fake-room',
    userId: 'private-user-id',
  }), /只允许 generals\.io 官方/)
})
