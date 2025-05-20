// src/components/QuickbooksSync.jsx
import React, { useState, useContext, useEffect } from 'react'; // Added useEffect if you plan to use it
import { AuthContext } from '../contexts/AuthContext';
import './QuickbooksSync.css';

const QuickbooksSync = () => {
    const [isLoading, setIsLoading] = useState(false);
    const [syncStatus, setSyncStatus] = useState('');
    const [lastSyncTime, setLastSyncTime] = useState(null);
    const [error, setError] = useState('');
    const { apiService } = useContext(AuthContext);

    const handleSync = async () => {
        setIsLoading(true);
        setError('');
        setSyncStatus('Initiating sync with QuickBooks...');
        try {
            // apiService.post ALREADY returns the parsed JSON data if successful,
            // or throws an error if not response.ok
            const data = await apiService.post('/quickbooks/trigger-sync', {});

            // Now, 'data' is the JSON object returned by the backend,
            // e.g., {"message": "Sync completed successfully. No pending items."}
            // or {"message": "...", "po_status": "...", "sales_status": "..."} if you revert the backend.
            
            // Check for the structure of your successful response from the backend
            // Based on the simplified backend response:
            if (data && data.message) {
                // If you revert to the more detailed backend response, use this:
                // setSyncStatus(`Sync triggered. PO Status: ${data.po_status || 'N/A'} | Sales Status: ${data.sales_status || 'N/A'}`);
                
                // For the current simplified backend response:
                setSyncStatus(data.message);
                
                setLastSyncTime(new Date().toLocaleString());
                setError('');
            } else {
                // This case might not be hit if apiService always throws for non-ok/non-JSON
                // but good as a fallback.
                setError(data.error || 'Sync completed but response format was unexpected.');
                setSyncStatus(`Warning: ${data.details || 'Sync response unclear.'}`);
            }

        } catch (err) { // Errors thrown by apiService will be caught here
            console.error("Error during QuickBooks sync:", err);
            // err.data might contain the JSON error details from the server if apiService attached it
            const errorMessage = err.data?.details || err.data?.error || err.message || 'Network error or server unavailable.';
            setError(`An error occurred: ${errorMessage}`);
            setSyncStatus('Sync process encountered an error.');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="quickbooks-sync-container">
            <h2>QuickBooks IIF Sync</h2>
            <p>
                This tool generates IIF files for new/updated Purchase Orders and Sales Orders (Invoices & Payments)
                that are pending synchronization with QuickBooks. The generated IIF files will be emailed.
            </p>
            
            <button onClick={handleSync} disabled={isLoading} className="sync-button">
                {isLoading ? 'Syncing...' : 'Generate & Email IIF Files Now (All Pending)'}
            </button>

            {/* Displaying error message if 'error' state is set */}
            {error && <div className="sync-status error">{error}</div>}
            {/* Displaying general sync status if no error OR if error also sets syncStatus */}
            {!error && syncStatus && <div className="sync-status success">{syncStatus}</div>} 
            
            {lastSyncTime && <p className="last-sync-time">Last sync attempt: {lastSyncTime}</p>}
        </div>
    );
};

export default QuickbooksSync;