// src/api/donors.js
import { apiGet, apiPost, apiPut } from "./client"

export const listDonors = () => apiGet("/donors") // requires the list endpoint above
export const createDonor = (payload) => apiPost("/donors", payload)
export const getDonor = (id) => apiGet(`/donors/${id}`)
export const replaceDonorHlaTypings = (id, entries) => apiPut(`/donors/${id}/hla-typings`, entries)
export const getDonorHlaTypings = (id) => apiGet(`/donors/${id}/hla-typings`)