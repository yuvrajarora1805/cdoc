const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const rateLimit = require('express-rate-limit');

const app = express();
const PORT = 3000;
const JWT_SECRET = 'super_secret_jwt_key_change_in_production';

app.use(cors());
app.use(express.json());

// SQLite DB initialization
const path = require('path');
const dbPath = process.env.DB_PATH || './database.sqlite';
const db = new sqlite3.Database(dbPath, (err) => {
    if (err) console.error(err.message);
    else console.log('Connected to the SQLite database.');
});

// Create tables
db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )`);

    db.run(`CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE,
        machine_id TEXT,
        active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )`);

    // Create default admin if not exists (username: admin, password: password123)
    db.get("SELECT * FROM admin WHERE username = 'admin'", async (err, row) => {
        if (!row) {
            const hash = await bcrypt.hash('password123', 10);
            db.run("INSERT INTO admin (username, password) VALUES ('admin', ?)", [hash]);
        }
    });
});

// Middleware: Authenticate JWT
const authenticateJWT = (req, res, next) => {
    const token = req.headers.authorization;
    if (token) {
        jwt.verify(token.split(' ')[1], JWT_SECRET, (err, user) => {
            if (err) return res.sendStatus(403);
            req.user = user;
            next();
        });
    } else {
        res.sendStatus(401);
    }
};

// Rate Limiter for Verify Endpoint
const verifyLimiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 50, // limit each IP to 50 requests per windowMs
    message: "Too many verification attempts, please try again later"
});

// Admin Login
app.post('/api/admin/login', (req, res) => {
    const { username, password } = req.body;
    db.get("SELECT * FROM admin WHERE username = ?", [username], async (err, user) => {
        if (err) return res.status(500).json({ error: 'Database error' });
        if (!user) return res.status(401).json({ error: 'Invalid credentials' });
        
        const match = await bcrypt.compare(password, user.password);
        if (match) {
            const token = jwt.sign({ username: user.username }, JWT_SECRET, { expiresIn: '2h' });
            res.json({ token });
        } else {
            res.status(401).json({ error: 'Invalid credentials' });
        }
    });
});

// Generate License (Admin Only)
app.post('/api/admin/generate', authenticateJWT, (req, res) => {
    const key = 'LIC-' + uuidv4().toUpperCase();
    db.run("INSERT INTO licenses (key) VALUES (?)", [key], function(err) {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ success: true, key });
    });
});

// List Licenses (Admin Only)
app.get('/api/admin/licenses', authenticateJWT, (req, res) => {
    db.all("SELECT * FROM licenses", (err, rows) => {
        if (err) return res.status(500).json({ error: err.message });
        res.json(rows);
    });
});

// Reset Machine ID (Admin Only)
app.post('/api/admin/reset', authenticateJWT, (req, res) => {
    const { key } = req.body;
    db.run("UPDATE licenses SET machine_id = NULL WHERE key = ?", [key], function(err) {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ success: true, message: 'Hardware ID reset.' });
    });
});

// Revoke License (Admin Only)
app.post('/api/admin/revoke', authenticateJWT, (req, res) => {
    const { key } = req.body;
    db.run("UPDATE licenses SET active = 0 WHERE key = ?", [key], function(err) {
        if (err) return res.status(500).json({ error: err.message });
        res.json({ success: true, message: 'License revoked.' });
    });
});

// Verify License (Used by Python App)
app.post('/api/verify', verifyLimiter, (req, res) => {
    const { key, machine_id } = req.body;
    if (!key || !machine_id) return res.status(400).json({ valid: false, message: 'Missing parameters' });

    db.get("SELECT * FROM licenses WHERE key = ?", [key], (err, row) => {
        if (err || !row) return res.json({ valid: false, message: 'Invalid license key' });
        if (!row.active) return res.json({ valid: false, message: 'License revoked' });

        if (!row.machine_id) {
            // First time use, bind machine ID
            db.run("UPDATE licenses SET machine_id = ? WHERE key = ?", [machine_id, key]);
            return res.json({ valid: true, message: 'License verified and bound to this machine.' });
        } else if (row.machine_id !== machine_id) {
            return res.json({ valid: false, message: 'License bound to another machine.' });
        }

        res.json({ valid: true, message: 'License valid' });
    });
});

app.listen(PORT, () => {
    console.log('Secure Licensing API running on port ' + PORT);
});
