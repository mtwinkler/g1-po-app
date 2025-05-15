// setAdminClaim.js
const admin = require('firebase-admin');
// IMPORTANT: Replace with the path to your service account key JSON file
const serviceAccount = require('./g1-po-app-77790-firebase-adminsdk-fbsvc-0ed84784ba.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const uidToSetClaimOn = 'USER_UID_TO_APPROVE'; // Get this UID from Firebase Auth console after the user signs in once
// Or use email to get UID:
// const emailToSetClaimOn = 'user@example.com';

async function setClaim() {
  try {
    // If using email to find UID:
    // const user = await admin.auth().getUserByEmail(emailToSetClaimOn);
    // const uidToSetClaimOn = user.uid;

    await admin.auth().setCustomUserClaims(uidToSetClaimOn, { isApproved: true }); // Your custom claim
    console.log(`Successfully set isApproved claim for UID: ${uidToSetClaimOn}`);

    // To verify (optional):
    const userWithClaims = await admin.auth().getUser(uidToSetClaimOn);
    console.log('User claims:', userWithClaims.customClaims);
  } catch (error) {
    console.error('Error setting custom claim:', error);
  }
  process.exit();
}

if (!uidToSetClaimOn /* && !emailToSetClaimOn */) {
    console.error("Please specify uidToSetClaimOn or emailToSetClaimOn in the script.");
} else {
    setClaim();
}