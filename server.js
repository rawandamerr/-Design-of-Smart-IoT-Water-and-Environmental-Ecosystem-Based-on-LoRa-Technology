require('dotenv').config();
const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const mqtt = require('mqtt');
const path = require('path');
const mysql = require('mysql2');
const { PythonShell } = require('python-shell');

const app = express();
const server = http.createServer(app);
const io = socketIo(server);

const PORT = process.env.PORT || 8080;

app.use(express.static(path.join(__dirname, 'public')));
app.use(express.json());

// ======================================================
// 1. DATABASE CONNECTION
// ======================================================
const db = mysql.createConnection({
    host: 'localhost',
    user: 'Leen',
    password: process.env.DB_PASSWORD || 'your_mariadb_password',
    database: 'SMART GREENHOUSE',
    enableKeepAlive: true
});

db.connect((err) => {
    if (err) {
        console.error('❌ MariaDB Connection Error:', err.message);
    } else {
        console.log('✅ Connected to MariaDB Database: SMART GREENHOUSE');
    }
});

// ======================================================
// 2. TTN MQTT CONFIGURATION
// ======================================================
const appId = process.env.TTN_APP_ID;
const apiKey = process.env.TTN_API_KEY;
const targetDevice = process.env.TTN_DEVICE_ID;
const ttnRegion = process.env.TTN_REGION || 'eu1';

const username = `${appId}@ttn`;

const mqttClient = mqtt.connect(
    `mqtts://${ttnRegion}.cloud.thethings.network`,
    {
        port: 8883,
        username: username,
        password: apiKey
    }
);

mqttClient.on('connect', () => {
    console.log(`✅ MQTT Connected to TTN Application: ${appId}`);

    mqttClient.subscribe(`v3/${username}/devices/+/up`, (err) => {
        if (err) {
            console.error('❌ Subscribe Error:', err.message);
        } else {
            console.log('📡 Subscribed to uplink topic');
        }
    });
});

mqttClient.on('error', (err) => {
    console.error('❌ MQTT Error:', err.message);
});

// ======================================================
// 3. PYTHON ML INTEGRATION
// ======================================================
const pyOptions = {
    mode: 'json',
    pythonOptions: ['-u'],
    scriptPath: __dirname,
    pythonPath: 'py'
};

const pyShell = new PythonShell(
    'ml_predictor_dashboard.py',
    pyOptions
);

pyShell.on('message', (results) => {
    console.log('🤖 ML Prediction:', results);

    io.emit('ml_prediction', results);
});

pyShell.on('error', (err) => {
    console.error('❌ Python Shell Error:', err);
});

// ======================================================
// 4. TTN UPLINK HANDLER
// ======================================================
mqttClient.on('message', (topic, buf) => {
    try {
        const msg = JSON.parse(buf.toString());

        // Check payload exists
        const payloadBase64 =
            msg.uplink_message?.frm_payload;

        if (!payloadBase64) {
            console.log('⚠️ No payload received');
            return;
        }

        // ==================================================
        // Decode Payload
        // ==================================================
        const bytes = Buffer.from(payloadBase64, 'base64');

        // Sensor values
        const tdsPPM = bytes.readUInt16LE(0);
        const uvV = bytes.readUInt16LE(2) / 100;
        const temp = bytes.readInt16LE(4) / 100;
        const pres = bytes.readUInt16LE(6) / 10;
        const alt = bytes.readInt16LE(8) / 10;

        // ==================================================
        // RSSI & SNR
        // ==================================================
        const metadata =
            msg.uplink_message?.rx_metadata?.[0] || {};

        const rssi = metadata.rssi ?? '--';
        const snr = metadata.snr ?? '--';

        // ==================================================
        // Packet Object
        // ==================================================
        const packet = {
            devId: msg.end_device_ids.device_id,
            temp: temp,
            tds: tdsPPM,
            uv: uvV,
            pressure: pres,
            altitude: alt,
            rssi: rssi,
            snr: snr,
            ts: Date.now()
        };

        // ==================================================
        // Console Output
        // ==================================================
        console.log('\n================================');
        console.log(`🚀 Device: ${packet.devId}`);
        console.log(`🌡️ Temperature : ${temp} °C`);
        console.log(`💧 TDS         : ${tdsPPM} PPM`);
        console.log(`☀️ UV Voltage  : ${uvV} V`);
        console.log(`📈 Pressure    : ${pres} hPa`);
        console.log(`⛰️ Altitude     : ${alt} m`);
        console.log(`📶 RSSI        : ${rssi} dBm`);
        console.log(`📡 SNR         : ${snr} dB`);
        console.log('================================\n');

        // ==================================================
        // SEND TO DASHBOARD
        // ==================================================
        io.emit('node1Data', packet);

        // ==================================================
        // SEND TO ML MODEL
        // ==================================================
        pyShell.send(packet);

        // ==================================================
        // SAVE TO DATABASE
        // ==================================================
        const sql = `
            INSERT INTO Readings
            (
                tds_ppm,
                uv_voltage,
                temperature,
                pressure,
                altitude,
                rssi,
                snr
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        `;

        db.query(
            sql,
            [
                tdsPPM,
                uvV,
                temp,
                pres,
                alt,
                rssi,
                snr
            ],
            (err) => {
                if (err) {
                    console.error(
                        '❌ Database Insert Error:',
                        err.message
                    );
                } else {
                    console.log(
                        `💾 Saved to DB | RSSI=${rssi} | SNR=${snr}`
                    );
                }
            }
        );

    } catch (e) {
        console.error('❌ Processing Error:', e.message);
    }
});

// ======================================================
// 5. SOCKET.IO CONNECTION
// ======================================================
io.on('connection', (socket) => {

    console.log('🖥️ Dashboard Client Connected');

    // ==============================================
    // Manual Alarm Downlink
    // ==============================================
    socket.on('manual_alarm', () => {

        const downlinkTopic =
            `v3/${username}/devices/${targetDevice}/down/push`;

        const payload = {
            downlinks: [
                {
                    f_port: 1,
                    frm_payload: "AQ==",
                    priority: "NORMAL"
                }
            ]
        };

        console.log(
            `📡 Sending Alarm Downlink to ${targetDevice}`
        );

        mqttClient.publish(
            downlinkTopic,
            JSON.stringify(payload),
            (err) => {
                if (err) {
                    console.error(
                        '❌ Downlink Failed:',
                        err.message
                    );
                } else {
                    console.log(
                        '📤 SUCCESS: Downlink Scheduled'
                    );
                }
            }
        );
    });

    // ==============================================
    // Disconnect
    // ==============================================
    socket.on('disconnect', () => {
        console.log('❌ Dashboard Client Disconnected');
    });
});

// ======================================================
// 6. START SERVER
// ======================================================
server.listen(PORT, () => {

    console.log('\n========================================');
    console.log('🚀 AGRIHYDRO AI SYSTEM LIVE');
    console.log(`🌐 Dashboard: http://localhost:${PORT}`);
    console.log('========================================\n');

});
