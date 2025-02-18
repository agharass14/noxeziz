const FLASK_SERVER_URL = "https://noxeziz.onrender.com/webhook"; // Replace with your Flask server URL

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  if (request.method === 'POST') {
    try {
      // Log incoming request details
      console.log('=== INCOMING REQUEST ===');
      console.log('Method:', request.method);
      console.log('URL:', request.url);
      console.log('Headers:', JSON.stringify([...request.headers]));

      // Clone the request to log the body without consuming it
      const clone = request.clone();
      const body = await clone.text();
      console.log('Request Body:', body);

      // Forward the request to the Flask server
      console.log('Forwarding request to Flask server:', FLASK_SERVER_URL);
      const response = await fetch(FLASK_SERVER_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body
      });

      // Log the response from the Flask server
      console.log('Flask server response status:', response.status);
      const responseBody = await response.text();
      console.log('Flask server response body:', responseBody);

      // Return the Flask server's response to the client
      return new Response(responseBody, {
        status: response.status,
        headers: response.headers
      });

    } catch (error) {
      // Log any errors that occur
      console.error('Error in handleRequest:', error);
      return new Response('Error forwarding request', { status: 500 });
    }
  }

  // Handle non-POST requests
  console.log('Received non-POST request');
  return new Response('Method not allowed', { status: 405 });
}