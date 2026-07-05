// src/api/client.js
const BASE_URL = "http://localhost:8090";

export async function apiGet(path){
    const response = await fetch(`${BASE_URL}${path}`);

    if(!response.ok){
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
}