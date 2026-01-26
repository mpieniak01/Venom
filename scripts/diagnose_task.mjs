
const TASK_ID = 'd0e45468-e8a4-45d8-b024-44d662cc69c4'; // known ID from logs
const BASE_URL = 'http://127.0.0.1:3000/api/v1/tasks';

async function check() {
    console.log(`Fetching task ${TASK_ID} from ${BASE_URL}/${TASK_ID}...`);
    try {
        const res = await fetch(`${BASE_URL}/${TASK_ID}`);
        console.log(`Status: ${res.status}`);
        if (!res.ok) {
            const text = await res.text();
            console.error('Error body:', text);
            return;
        }
        const json = await res.json();
        console.log('Result:', JSON.stringify(json, null, 2));
    } catch (err) {
        console.error('Fetch failed:', err);
    }
}

check();
