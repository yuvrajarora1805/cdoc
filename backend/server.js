const express = require('express');
const mysql = require('mysql2/promise');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const cors = require('cors');
const { v4: uuidv4 } = require('uuid');
const rateLimit = require('express-rate-limit');

const app = express();
const PORT = 3000;
const JWT_SECRET = process.env.JWT_SECRET || 'super_secret_jwt_key_change_in_production';

app.use(cors());
app.use(express.json());

// MySQL connection pool
const pool = mysql.createPool({
    host:     process.env.DB_HOST     || 'mysql',
    port:     process.env.DB_PORT     || 3306,
    user:     process.env.DB_USER     || 'license_user',
    password: process.env.DB_PASSWORD || 'license_pass',
    database: process.env.DB_NAME     || 'license_db',
    waitForConnections: true,
    connectionLimit: 10,
    queueLimit: 0
});

// Initialize tables and default admin
async function initDB() {
    let retries = 10;
    while (retries > 0) {
        try {
            const conn = await pool.getConnection();
            console.log('Connected to MySQL database.');

            await conn.execute(`
                CREATE TABLE IF NOT EXISTS admin (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            `);

            await conn.execute(`
                CREATE TABLE IF NOT EXISTS licenses (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    \`key\` VARCHAR(255) UNIQUE NOT NULL,
                    machine_id VARCHAR(255) DEFAULT NULL,
                    active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME DEFAULT NULL
                )
            `);

            // Create default admin if not exists
            const [rows] = await conn.execute("SELECT * FROM admin WHERE username = 'admin'");
            if (rows.length === 0) {
                const hash = await bcrypt.hash('password123', 10);
                await conn.execute("INSERT INTO admin (username, password) VALUES ('admin', ?)", [hash]);
                console.log('Default admin created: admin / password123');
            }

            conn.release();
            break;
        } catch (err) {
            retries--;
            console.log(`DB not ready, retrying... (${retries} left). Error: ${err.message}`);
            await new Promise(r => setTimeout(r, 3000));
        }
    }
    if (retries === 0) {
        console.error('Could not connect to MySQL after multiple attempts. Exiting.');
        process.exit(1);
    }
}

initDB().then(() => {
    app.listen(PORT, () => {
        console.log('Secure Licensing API running on port ' + PORT);
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
    windowMs: 15 * 60 * 1000,
    max: 50,
    message: "Too many verification attempts, please try again later"
});

// ── Admin Login ──────────────────────────────────────────────────────────────
app.post('/api/admin/login', async (req, res) => {
    const { username, password } = req.body;
    try {
        const [rows] = await pool.execute("SELECT * FROM admin WHERE username = ?", [username]);
        if (rows.length === 0) return res.status(401).json({ error: 'Invalid credentials' });

        const match = await bcrypt.compare(password, rows[0].password);
        if (match) {
            const token = jwt.sign({ username: rows[0].username }, JWT_SECRET, { expiresIn: '2h' });
            res.json({ token });
        } else {
            res.status(401).json({ error: 'Invalid credentials' });
        }
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── Generate License ─────────────────────────────────────────────────────────
app.post('/api/admin/generate', authenticateJWT, async (req, res) => {
    const key = 'LIC-' + uuidv4().toUpperCase();
    const days = parseInt(req.body.days) || 365;

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + days);

    try {
        await pool.execute("INSERT INTO licenses (`key`, expires_at) VALUES (?, ?)", [key, expiresAt]);
        res.json({ success: true, key, expires_at: expiresAt });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── List Licenses ────────────────────────────────────────────────────────────
app.get('/api/admin/licenses', authenticateJWT, async (req, res) => {
    try {
        const [rows] = await pool.execute("SELECT * FROM licenses ORDER BY id DESC");
        res.json(rows);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── Reset Machine ID ─────────────────────────────────────────────────────────
app.post('/api/admin/reset', authenticateJWT, async (req, res) => {
    const { key } = req.body;
    try {
        await pool.execute("UPDATE licenses SET machine_id = NULL WHERE `key` = ?", [key]);
        res.json({ success: true, message: 'Hardware ID reset.' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── Revoke License ───────────────────────────────────────────────────────────
app.post('/api/admin/revoke', authenticateJWT, async (req, res) => {
    const { key } = req.body;
    try {
        await pool.execute("UPDATE licenses SET active = 0 WHERE `key` = ?", [key]);
        res.json({ success: true, message: 'License revoked.' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── Extend License Expiry ────────────────────────────────────────────────────
app.post('/api/admin/extend', authenticateJWT, async (req, res) => {
    const { key, days } = req.body;
    if (!key || !days) return res.status(400).json({ error: 'Missing key or days' });

    try {
        const [rows] = await pool.execute("SELECT expires_at FROM licenses WHERE `key` = ?", [key]);
        if (rows.length === 0) return res.status(404).json({ error: 'License not found' });

        const base = rows[0].expires_at && new Date(rows[0].expires_at) > new Date()
            ? new Date(rows[0].expires_at)
            : new Date();

        base.setDate(base.getDate() + parseInt(days));
        await pool.execute("UPDATE licenses SET expires_at = ? WHERE `key` = ?", [base, key]);
        res.json({ success: true, new_expiry: base });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ── Verify License (Python App) ──────────────────────────────────────────────
app.post('/api/verify', verifyLimiter, async (req, res) => {
    const { key, machine_id } = req.body;
    if (!key || !machine_id) return res.status(400).json({ valid: false, message: 'Missing parameters' });

    try {
        const [rows] = await pool.execute("SELECT * FROM licenses WHERE `key` = ?", [key]);
        if (rows.length === 0) return res.json({ valid: false, message: 'Invalid license key' });

        const lic = rows[0];
        if (!lic.active) return res.json({ valid: false, message: 'License revoked' });

        // Check expiry
        if (lic.expires_at) {
            const expiry = new Date(lic.expires_at);
            if (expiry < new Date()) {
                return res.json({ valid: false, message: 'License expired on ' + expiry.toDateString() });
            }
        }

        if (!lic.machine_id) {
            // First use — bind to machine
            await pool.execute("UPDATE licenses SET machine_id = ? WHERE `key` = ?", [machine_id, key]);
            return res.json({ valid: true, message: 'License verified and bound to this machine.' });
        } else if (lic.machine_id !== machine_id) {
            return res.json({ valid: false, message: 'License bound to another machine.' });
        }

        res.json({ valid: true, message: 'License valid' });
    } catch (err) {
        res.status(500).json({ valid: false, message: 'Server error: ' + err.message });
    }
});
