/**
 * RFP Response Assistant — API client.
 * All requests go to the relative `/api` base, which the Vite dev server proxies
 * to the FastAPI backend (default port 4010). In production the static build is
 * expected to be served behind the same origin as the API.
 */

const API_BASE = '/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  
  const headers = {
    'Accept': 'application/json',
    ...options.headers,
  };

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const config = {
    ...options,
    headers,
  };

  if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
    config.body = JSON.stringify(options.body);
  }

  try {
    const response = await fetch(url, config);

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('content-type');
    let data;
    if (contentType && contentType.includes('application/json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errorMsg = (data && data.detail) 
        ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
        : (data && data.message ? data.message : `HTTP error ${response.status}: ${response.statusText}`);
      const error = new Error(errorMsg);
      error.status = response.status;
      error.data = data;
      throw error;
    }

    return data;
  } catch (err) {
    console.error(`[API Error] ${options.method || 'GET'} ${url}:`, err);
    throw err;
  }
}

export const api = {
  // --- Health ---
  getHealth: () => request('/health'),

  // --- Settings (F03) ---
  getSettings: () => request('/settings'),
  updateSettings: (settingsData) => request('/settings', {
    method: 'PUT',
    body: settingsData,
  }),

  // --- Services Management (F04) ---
  getServices: () => request('/services'),
  createService: (serviceData) => request('/services', {
    method: 'POST',
    body: serviceData,
  }),
  deleteService: (id) => request(`/services/${id}`, {
    method: 'DELETE',
  }),

  // --- RFP Core (F01, F06, F07, F26) ---
  getRFPs: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.client) params.append('client', filters.client);
    if (filters.status) params.append('status', filters.status);
    if (filters.outcome) params.append('outcome', filters.outcome);
    if (filters.service_id) params.append('service_id', filters.service_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    return request(`/rfps${query}`);
  },
  getRFP: (id) => request(`/rfps/${id}`),
  createRFP: (rfpData) => request('/rfps', {
    method: 'POST',
    body: rfpData,
  }),
  updateRFP: (id, rfpData) => request(`/rfps/${id}`, {
    method: 'PUT',
    body: rfpData,
  }),
  uploadRFP: (formData) => request('/rfps/upload', {
    method: 'POST',
    body: formData,
  }),

  // --- Sections & Classification (F09, F10, F18) ---
  classifyRFP: (rfpId) => request(`/rfps/${rfpId}/classify`, {
    method: 'POST',
  }),
  classifySections: (rfpId) => request(`/rfps/${rfpId}/classify`, {
    method: 'POST',
  }),
  updateSection: (rfpId, sectionId, sectionData) => request(`/rfps/${rfpId}/sections/${sectionId}`, {
    method: 'PUT',
    body: sectionData,
  }),
  addSection: (rfpId, sectionData) => request(`/rfps/${rfpId}/sections`, {
    method: 'POST',
    body: sectionData,
  }),
  deleteSection: (rfpId, sectionId) => request(`/rfps/${rfpId}/sections/${sectionId}`, {
    method: 'DELETE',
  }),
  reorderSections: (rfpId, sectionIds) => request(`/rfps/${rfpId}/sections/reorder`, {
    method: 'PUT',
    body: { section_ids: sectionIds },
  }),
  generateSectionDraft: (rfpId, sectionId) => request(`/rfps/${rfpId}/sections/${sectionId}/generate`, {
    method: 'POST',
  }),

  // --- Account Manager Notes (F17) ---
  getNotes: (rfpId) => request(`/rfps/${rfpId}/notes`),
  createNote: (rfpId, noteData) => request(`/rfps/${rfpId}/notes`, {
    method: 'POST',
    body: noteData,
  }),
  deleteNote: (rfpId, noteId) => request(`/rfps/${rfpId}/notes/${noteId}`, {
    method: 'DELETE',
  }),

  // --- Open Questions (F20) ---
  getOpenQuestions: (rfpId) => request(`/rfps/${rfpId}/open-questions`),
  resolveOpenQuestion: (rfpId, questionId, resolutionData) => request(`/rfps/${rfpId}/open-questions/${questionId}`, {
    method: 'PUT',
    body: resolutionData,
  }),

  // --- Batch draft generation ---
  generateAllDrafts: (rfpId, options = {}) => request(`/rfps/${rfpId}/generate-all`, {
    method: 'POST',
    body: options,
  }),

  // --- Google Docs Export (F23, F24) ---
  exportToGoogleDocs: (rfpId) => request(`/rfps/${rfpId}/export`, {
    method: 'POST',
  }),

  // --- Knowledge Base & RAG (F11, F12, F13, F16) ---
  getKBDocuments: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.query) params.append('query', filters.query);
    if (filters.type) params.append('type', filters.type);
    if (filters.outcome) params.append('outcome', filters.outcome);
    if (filters.service_id) params.append('service_id', filters.service_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    return request(`/kb${query}`);
  },
  getKBDocument: (id) => request(`/kb/${id}`),
  createKBDocument: (docData) => request('/kb', {
    method: 'POST',
    body: docData,
  }),
  updateKBDocument: (id, docData) => request(`/kb/${id}`, {
    method: 'PUT',
    body: docData,
  }),
  deleteKBDocument: (id) => request(`/kb/${id}`, {
    method: 'DELETE',
  }),
  seedKBDocuments: () => request('/kb/seed', { method: 'POST' }),

  // --- Structured Pricing (F14, F15) ---
  getPriceItems: (filters = {}) => {
    const params = new URLSearchParams();
    if (filters.service_id) params.append('service_id', filters.service_id);
    const query = params.toString() ? `?${params.toString()}` : '';
    return request(`/pricing${query}`);
  },
  createPriceItem: (priceData) => request('/pricing', {
    method: 'POST',
    body: priceData,
  }),
  updatePriceItem: (id, priceData) => request(`/pricing/${id}`, {
    method: 'PUT',
    body: priceData,
  }),
  deletePriceItem: (id) => request(`/pricing/${id}`, {
    method: 'DELETE',
  }),
  seedPriceItems: () => request('/pricing/seed', { method: 'POST' }),
};

