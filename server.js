const express = require('express');
const http = require('http');
const { Server } = require('socket.io');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

// public 폴더의 정적 파일(HTML, JS 등)을 서비스합니다.
app.use(express.static('public'));

// 방 데이터 및 플레이어 세션 관리
const rooms = {}; // 구조: { 방코드: { players: { 소켓ID: { x, y, color } } } }
const socketRoomMap = {}; // 구조: { 소켓ID: 방코드 }

io.on('connection', (socket) => {
    console.log(`플레이어 접속: ${socket.id}`);

    // [방 생성] 이벤트
    socket.on('createRoom', () => {
        // 랜덤한 5자리 대문자 방 코드 생성
        const roomCode = Math.random().toString(36).substring(2, 7).toUpperCase();
        rooms[roomCode] = { players: {} };

        joinPlayerToRoom(socket, roomCode);
        socket.emit('roomCreated', roomCode);
    });

    // [방 참여] 이벤트
    socket.on('joinRoom', (roomCode) => {
        if (rooms[roomCode]) {
            joinPlayerToRoom(socket, roomCode);
            socket.emit('roomJoined', roomCode);
        } else {
            socket.emit('errorMsg', '존재하지 않는 방 번호입니다.');
        }
    });

    // [WASD 이동] 이벤트
    socket.on('move', (keys) => {
        const roomCode = socketRoomMap[socket.id];
        if (!roomCode || !rooms[roomCode]) return;

        const player = rooms[roomCode].players[socket.id];
        if (!player) return;

        const SPEED = 5;
        if (keys.up) player.y -= SPEED;
        if (keys.down) player.y += SPEED;
        if (keys.left) player.x -= SPEED;
        if (keys.right) player.x += SPEED;

        // 해당 방에 있는 모든 플레이어에게 업데이트된 위치 전송
        io.to(roomCode).emit('updatePlayers', rooms[roomCode].players);
    });

    // [접속 종료] 이벤트
    socket.on('disconnect', () => {
        const roomCode = socketRoomMap[socket.id];
        if (roomCode && rooms[roomCode]) {
            delete rooms[roomCode].players[socket.id];
            delete socketRoomMap[socket.id];

            // 다른 플레이어들에게 이탈 알림 및 데이터 갱신
            io.to(roomCode).emit('updatePlayers', rooms[roomCode].players);

            // 방에 아무도 없으면 방 삭제
            if (Object.keys(rooms[roomCode].players).length === 0) {
                delete rooms[roomCode];
            }
        }
        console.log(`플레이어 접속 종료: ${socket.id}`);
    });
});

// 플레이어를 특정 방에 참가시키는 공통 함수
function joinPlayerToRoom(socket, roomCode) {
    socket.join(roomCode);
    socketRoomMap[socket.id] = roomCode;

    // 초기 위치 및 랜덤 색상 부여
    rooms[roomCode].players[socket.id] = {
        x: 400,
        y: 300,
        color: '#' + Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0')
    };

    // 방 안의 모두에게 최신 플레이어 목록 전송
    io.to(roomCode).emit('updatePlayers', rooms[roomCode].players);
}

const PORT = 3000;
server.listen(PORT, () => {
    console.log(`서버가 구동되었습니다! http://localhost:${PORT}`);
});