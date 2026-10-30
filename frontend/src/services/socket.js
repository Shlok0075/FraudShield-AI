/**
 * FraudShield AI - Socket.IO client (PART 13 / Week 11 Day 2)
 * ===============================================================
 * Connects to the backend's mounted Socket.IO server and listens for
 * new_transaction / new_alert / alert_updated events. Reconnection is
 * handled automatically by socket.io-client's defaults (Week 11 Day 6).
 */
import { io } from 'socket.io-client'
import { API_BASE_URL } from './api'

let socket = null

export function getSocket() {
  if (!socket) {
    socket = io(API_BASE_URL, {
      path: '/socket.io',
      transports: ['websocket', 'polling'],
      autoConnect: true,
    })
  }
  return socket
}

export function disconnectSocket() {
  if (socket) {
    socket.disconnect()
    socket = null
  }
}
