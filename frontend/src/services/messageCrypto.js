const DB_NAME = 'vanish-crypto'
const STORE_NAME = 'identities'
const ALLOWED_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function readIdentity(userId) {
  const database = await openDatabase()
  return new Promise((resolve, reject) => {
    const request = database.transaction(STORE_NAME).objectStore(STORE_NAME).get(userId)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  }).finally(() => database.close())
}

function bytesToBase64(bytes) {
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
  }
  return btoa(binary)
}

function base64ToBytes(value) {
  const binary = atob(value)
  return Uint8Array.from(binary, (character) => character.charCodeAt(0))
}

async function importPublicKey(value) {
  return crypto.subtle.importKey(
    'jwk',
    JSON.parse(value),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt'],
  )
}

async function encryptBytes(plaintext, senderPublicKey, recipientPublicKey) {
  if (!senderPublicKey || !recipientPublicKey) throw new Error('Both participants must set up encryption first.')
  const contentKey = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt'])
  const rawKey = new Uint8Array(await crypto.subtle.exportKey('raw', contentKey))
  const nonce = crypto.getRandomValues(new Uint8Array(12))
  const [ciphertext, senderKey, recipientKey] = await Promise.all([
    crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, contentKey, plaintext),
    importPublicKey(senderPublicKey).then((key) => crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, rawKey)),
    importPublicKey(recipientPublicKey).then((key) => crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, rawKey)),
  ])
  return {
    ciphertext: new Uint8Array(ciphertext),
    nonce: bytesToBase64(nonce),
    senderKey: bytesToBase64(new Uint8Array(senderKey)),
    recipientKey: bytesToBase64(new Uint8Array(recipientKey)),
  }
}

async function decryptBytes(payload, user) {
  const identity = await readIdentity(user.id)
  if (!identity?.privateKey || identity.publicKey !== user.public_key) {
    throw new Error('This browser does not have the private key for this message.')
  }
  const rawKey = await crypto.subtle.decrypt(
    { name: 'RSA-OAEP' },
    identity.privateKey,
    base64ToBytes(payload.encrypted_key),
  )
  const contentKey = await crypto.subtle.importKey('raw', rawKey, 'AES-GCM', false, ['decrypt'])
  return new Uint8Array(await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: base64ToBytes(payload.nonce) },
    contentKey,
    base64ToBytes(payload.ciphertext),
  ))
}

function matchesImageSignature(type, bytes) {
  if (type === 'image/jpeg') return bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff
  if (type === 'image/png') return bytes.length >= 8 && bytes.slice(0, 8).every((value, index) => value === [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a][index])
  if (type === 'image/gif') return new TextDecoder().decode(bytes.slice(0, 6)) === 'GIF87a' || new TextDecoder().decode(bytes.slice(0, 6)) === 'GIF89a'
  if (type === 'image/webp') return bytes.length >= 12 && new TextDecoder().decode(bytes.slice(0, 4)) === 'RIFF' && new TextDecoder().decode(bytes.slice(8, 12)) === 'WEBP'
  return false
}

export async function generateIdentity() {
  const keys = await crypto.subtle.generateKey(
    { name: 'RSA-OAEP', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
    false,
    ['encrypt', 'decrypt'],
  )
  const publicKey = JSON.stringify(await crypto.subtle.exportKey('jwk', keys.publicKey))
  return { publicKey, privateKey: keys.privateKey }
}

export async function storeIdentity(userId, identity) {
  const database = await openDatabase()
  await new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).put(identity, userId)
    transaction.oncomplete = resolve
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
  }).finally(() => database.close())
}

export async function stageIdentity(username, identity) {
  await storeIdentity(`pending:${username.toLowerCase()}`, identity)
}

export async function adoptPendingIdentity(username, user) {
  const pendingKey = `pending:${username.toLowerCase()}`
  const identity = await readIdentity(pendingKey)
  if (!identity?.privateKey || identity.publicKey !== user.public_key) return false
  await storeIdentity(user.id, identity)
  const database = await openDatabase()
  await new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, 'readwrite')
    transaction.objectStore(STORE_NAME).delete(pendingKey)
    transaction.oncomplete = resolve
    transaction.onerror = () => reject(transaction.error)
    transaction.onabort = () => reject(transaction.error)
  }).finally(() => database.close())
  return true
}

export async function hasIdentity(user) {
  const identity = await readIdentity(user.id)
  return Boolean(identity?.privateKey && identity.publicKey === user.public_key)
}

export async function encryptImage(file, senderPublicKey, recipientPublicKey) {
  if (!ALLOWED_TYPES.has(file.type)) throw new Error('Only JPEG, PNG, GIF, and WebP images are supported.')
  if (file.size > 5 * 1024 * 1024) throw new Error('Image must be 5 MB or smaller.')

  const metadata = new TextEncoder().encode(JSON.stringify({
    name: file.name.slice(0, 255),
    type: file.type,
  }))
  const image = new Uint8Array(await file.arrayBuffer())
  if (!matchesImageSignature(file.type, image)) throw new Error('The selected file is not a valid supported image.')
  const plaintext = new Uint8Array(4 + metadata.length + image.length)
  new DataView(plaintext.buffer).setUint32(0, metadata.length)
  plaintext.set(metadata, 4)
  plaintext.set(image, 4 + metadata.length)

  const encrypted = await encryptBytes(plaintext, senderPublicKey, recipientPublicKey)

  return {
    ...encrypted,
    ciphertext: new Blob([encrypted.ciphertext], { type: 'application/octet-stream' }),
  }
}

export async function decryptImage(payload, user) {
  const plaintext = await decryptBytes(payload, user)
  if (plaintext.length < 5) throw new Error('Invalid encrypted image')
  const metadataLength = new DataView(plaintext.buffer, plaintext.byteOffset, plaintext.byteLength).getUint32(0)
  if (metadataLength > 4096 || 4 + metadataLength >= plaintext.length) throw new Error('Invalid encrypted image')
  const metadata = JSON.parse(new TextDecoder().decode(plaintext.subarray(4, 4 + metadataLength)))
  if (!ALLOWED_TYPES.has(metadata.type)) throw new Error('Unsupported encrypted image type')
  return {
    blob: new Blob([plaintext.subarray(4 + metadataLength)], { type: metadata.type }),
    name: metadata.name || 'Disappearing image',
  }
}

export async function encryptText(content, senderPublicKey, recipientPublicKey) {
  const plaintext = new TextEncoder().encode(content)
  if (!plaintext.length) throw new Error('Message cannot be blank.')
  const encrypted = await encryptBytes(plaintext, senderPublicKey, recipientPublicKey)
  return { ...encrypted, ciphertext: bytesToBase64(encrypted.ciphertext) }
}

export async function decryptText(message, user) {
  const plaintext = await decryptBytes(message, user)
  const content = new TextDecoder('utf-8', { fatal: true }).decode(plaintext)
  if (!content) throw new Error('Invalid encrypted message')
  return content
}
