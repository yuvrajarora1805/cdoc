const crypto = require('crypto');
const fs = require('fs');

// Usage: node generate_offline_license.js <license_key> <machine_id> <expires_at> <private_key_file>
// Example: node generate_offline_license.js LIC-12345 1234567890 2027-01-01 private.pem

const args = process.argv.slice(2);
if (args.length < 4) {
    console.error('Usage: node generate_offline_license.js <license_key> <machine_id> <expires_at_iso> <path_to_private_key_pem>');
    console.error('Example: node generate_offline_license.js LIC-ABC 123456 2027-12-31T23:59:59.000Z private.pem');
    process.exit(1);
}

const key = args[0];
const machine_id = args[1];
const expires_at = args[2] === 'null' ? null : args[2];
const privateKeyPath = args[3];

const privateKey = fs.readFileSync(privateKeyPath, 'utf8');

const licenseData = {
    key: key,
    machine_id: machine_id,
    expires_at: expires_at
};

const dataToSign = JSON.stringify(licenseData);

const sign = crypto.createSign('SHA256');
sign.update(dataToSign);
sign.end();
const signature = sign.sign(privateKey, 'hex');

const licenseFileContent = {
    license_data: licenseData,
    signature: signature
};

fs.writeFileSync('license.lic', JSON.stringify(licenseFileContent, null, 4));
console.log('Successfully generated offline license.lic file!');
console.log(JSON.stringify(licenseFileContent, null, 4));
