/**
 * CORS headers for Azure Functions responses.
 * Used to allow cross-origin requests from the frontend.
 * Note: In production on SWA, CORS is handled by the platform.
 */
export const corsHeaders = {
    'Access-Control-Allow-Origin': '*',  // Allow all origins for local dev
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400'
};

/**
 * Helper to add CORS headers to a response
 */
export function withCors(response: { status?: number; jsonBody?: any; body?: any }): { 
    status?: number; 
    jsonBody?: any; 
    body?: any; 
    headers: Record<string, string> 
} {
    return {
        ...response,
        headers: corsHeaders
    };
}

/**
 * Response for OPTIONS preflight requests
 */
export const corsPreflightResponse = {
    status: 204,
    headers: corsHeaders
};
