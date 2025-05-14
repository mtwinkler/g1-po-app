// --- START OF FILE OrderDetail.jsx ---

// OrderDetail.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import './OrderDetail.css';

// --- Helper function for debouncing ---
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);
    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);
  return debouncedValue;
}

// Helper function for Brokerbin links
const createBrokerbinLink = (partNumber) => {
  if (!partNumber) return '#';
  const encodedPartNumber = encodeURIComponent(partNumber);
  return `https://members.brokerbin.com/partkey?login=g1tech&parts=${encodedPartNumber}`;
};

// Helper to escape regex special characters
function escapeRegExp(string) {
  if (typeof string !== 'string') return ''; // Add type check
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// --- NEW Helper function to format shipping method ---
const formatShippingMethod = (methodString) => {
  if (!methodString || typeof methodString !== 'string') {
    return 'N/A';
  }
  const match = methodString.match(/\(([^)]+)\)/);
  if (match && match[1]) {
    return match[1];
  }
  return methodString;
};


function OrderDetail() {
  const { orderId } = useParams();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false); // For the main "PROCESS ORDER" button
  const [processSuccess, setProcessSuccess] = useState(null);
  const [processError, setProcessError] = useState(null);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');
  const [manualStatusUpdateInProgress, setManualStatusUpdateInProgress] = useState(false);


  const [selectedSupplierId, setSelectedSupplierId] = useState('');
  const [poNotes, setPoNotes] = useState('');
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [shipmentMethod, setShipmentMethod] = useState('');
  const [shipmentWeight, setShipmentWeight] = useState('');

  const setPurchaseItemsRef = useRef(setPurchaseItems);
  useEffect(() => { setPurchaseItemsRef.current = setPurchaseItems; }, []);
  const purchaseItemsRef = useRef(purchaseItems);
  useEffect(() => { purchaseItemsRef.current = purchaseItems; }, [purchaseItems]);

  const cleanPullSuffix = " - clean pull";

  const fetchOrderAndSuppliers = useCallback(async (signal) => {
    setLoading(true); setError(null); /*setOrderData(null);*/ setProcessSuccess(null); setProcessError(null); setStatusUpdateMessage('');
    try {
        const orderApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}`;
        const suppliersApiUrl = `${VITE_API_BASE_URL}/suppliers`;
        const orderResponse = await fetch(orderApiUrl, { signal });
        const suppliersResponse = await fetch(suppliersApiUrl, { signal });
        if (!orderResponse.ok) {
            let errorMsg = `Order fetch failed: ${orderResponse.status}`;
            try { const errorData = await orderResponse.json(); errorMsg = errorData.details || errorData.error || errorMsg; } catch (parseError) {}
            throw new Error(errorMsg);
        }
         if (!suppliersResponse.ok) {
            let errorMsg = `Supplier fetch failed: ${suppliersResponse.status}`;
            try { const errorData = await suppliersResponse.json(); errorMsg = errorData.error || errorMsg; } catch (parseError) { }
            throw new Error(errorMsg);
        }
        const fetchedOrderData = await orderResponse.json();
        const fetchedSuppliers = await suppliersResponse.json();
        setOrderData(fetchedOrderData);
        setSuppliers(fetchedSuppliers || []);
        if (fetchedOrderData?.order) {
            let defaultMethodForForm = 'UPS Ground';
            const customerMethodRaw = fetchedOrderData.order.customer_shipping_method;
            const parsedCustomerMethodForForm = formatShippingMethod(customerMethodRaw);
            if (parsedCustomerMethodForForm && typeof parsedCustomerMethodForForm === 'string') {
                const methodLower = parsedCustomerMethodForForm.toLowerCase();
                if (methodLower.includes('ground')) { defaultMethodForForm = 'UPS Ground'; }
                else if (methodLower.includes('2nd day') || methodLower.includes('second day')) { defaultMethodForForm = 'UPS 2nd Day Air'; }
                else if (methodLower.includes('next day') || methodLower.includes('nda')) { defaultMethodForForm = 'UPS Next Day Air'; }
                 else if (customerMethodRaw && typeof customerMethodRaw === 'string' && customerMethodRaw.toLowerCase().includes('free shipping')) {
                    defaultMethodForForm = 'UPS Ground';
                }
            }
            setShipmentMethod(defaultMethodForForm);
        }
        if (fetchedOrderData?.line_items) {
            const initialItems = fetchedOrderData.line_items.map(item => {
                const initialSku = item.hpe_option_pn || item.original_sku || '';
                let initialDescription = item.hpe_po_description || item.line_item_name || '';
                if (initialDescription && typeof initialDescription === 'string' && !initialDescription.endsWith(cleanPullSuffix)) {
                    initialDescription += cleanPullSuffix;
                } else if (!initialDescription) {
                    initialDescription = cleanPullSuffix.trim();
                }
                return {
                    original_order_line_item_id: item.line_item_id,
                    sku: initialSku, description: initialDescription, skuInputValue: initialSku,
                    quantity: item.quantity || 1, unit_cost: '', condition: 'New',
                    original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn,
                    original_name: item.line_item_name, hpe_po_description: item.hpe_po_description,
                };
            });
            setPurchaseItemsRef.current(initialItems);
        } else {
            setPurchaseItemsRef.current([]);
        }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message || "An unknown error occurred during data fetching.");
      }
    } finally {
        setLoading(false);
    }
  }, [orderId, cleanPullSuffix, VITE_API_BASE_URL]);

  useEffect(() => {
    const abortController = new AbortController();
    if (orderId) {
        fetchOrderAndSuppliers(abortController.signal);
    } else {
        setError(new Error("Order ID is missing in the URL."));
        setLoading(false);
    }
    return () => abortController.abort();
  }, [orderId, fetchOrderAndSuppliers]);

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  useEffect(() => {
    const abortController = new AbortController();
    const fetchDescription = async () => {
      if (debouncedSku && typeof debouncedSku === 'string' && skuToLookup.index !== -1) {
        const lookupApiUrl = `${VITE_API_BASE_URL}/lookup/description/${encodeURIComponent(debouncedSku)}`;
        try {
          const response = await fetch(lookupApiUrl, { signal: abortController.signal });
          if (response.ok) {
            const data = await response.json();
            const currentItems = purchaseItemsRef.current;
            const updatedItems = [...currentItems];
            if (updatedItems[skuToLookup.index] && updatedItems[skuToLookup.index].sku === debouncedSku) {
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) {
                    newDescription += cleanPullSuffix;
                } else if (newDescription === null || newDescription === undefined || newDescription === "") {
                    const existingDescWithoutSuffix = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDescWithoutSuffix ? existingDescWithoutSuffix + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) {
                        newDescription = cleanPullSuffix.trim();
                    }
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
                setPurchaseItemsRef.current(updatedItems);
            }
          }
        } catch (error) { if (error.name !== 'AbortError') console.error("Error fetching description:", error); }
      }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, VITE_API_BASE_URL]);

  const handleSupplierChange = (e) => {
    const newSupplierId = e.target.value;
    setSelectedSupplierId(newSupplierId);
    const supplierIdInt = parseInt(newSupplierId, 10);
    const selectedSupplier = suppliers.find(s => s.id === supplierIdInt);
    let extractedNotes = '';
    if (selectedSupplier && selectedSupplier.defaultponotes !== null && selectedSupplier.defaultponotes !== undefined) {
        extractedNotes = selectedSupplier.defaultponotes;
    }
    setPoNotes(extractedNotes);
  };

  const handlePoNotesChange = (e) => { setPoNotes(e.target.value); };

  const handlePurchaseItemChange = (index, field, value) => {
    const currentItems = purchaseItemsRef.current;
    const updatedItems = [...currentItems];
    const itemToUpdate = { ...updatedItems[index] };
    itemToUpdate[field] = value;
    if (field === 'sku') {
      setSkuToLookup({ index, sku: value });
    }
    updatedItems[index] = itemToUpdate;
    setPurchaseItemsRef.current(updatedItems);
  };

  const handleShipmentMethodChange = (e) => { setShipmentMethod(e.target.value); };
  const handleShipmentWeightChange = (e) => { setShipmentWeight(e.target.value); };

  const handleCopyToClipboard = async (textToCopy) => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(String(textToCopy));
      setClipboardStatus(`Copied: ${textToCopy}`);
      setTimeout(() => setClipboardStatus(''), 1500);
    } catch (err) {
      setClipboardStatus('Failed to copy!');
      setTimeout(() => setClipboardStatus(''), 1500);
    }
  };

  const handleBrokerbinLinkClick = async (e, partNumber) => {
    setStatusUpdateMessage('');
    if (orderData?.order?.status && typeof orderData.order.status === 'string' && orderData.order.status.toLowerCase() === 'new') {
      const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
      try {
        const response = await fetch(statusApiUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'RFQ Sent' }),
        });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) throw new Error(responseData?.details || responseData?.error || `HTTP error! Status: ${response.status}`);
        // Re-fetch data instead of optimistic update for Brokerbin clicks to ensure consistency
        const abortController = new AbortController();
        await fetchOrderAndSuppliers(abortController.signal);
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${partNumber}`);
      } catch (err) {
        setStatusUpdateMessage(`Error updating status: ${err.message}`);
      }
    } else if (orderData?.order?.status && typeof orderData.order.status === 'string' && orderData.order.status.toLowerCase() !== 'rfq sent' && orderData.order.status.toLowerCase() !== 'processed') {
      setStatusUpdateMessage(`Order status is not 'new'. Cannot update to RFQ Sent.`);
    }
  };

  const handleManualStatusUpdate = async (newStatus) => {
    if (!orderId || !VITE_API_BASE_URL) {
        setStatusUpdateMessage("Error: Configuration issue.");
        return;
    }
    setManualStatusUpdateInProgress(true);
    setStatusUpdateMessage('');
    const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
    try {
        const response = await fetch(statusApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) throw new Error(responseData?.details || responseData?.error || `HTTP error! Status: ${response.status}`);
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        // Re-fetch order data after successful update
        const abortController = new AbortController();
        await fetchOrderAndSuppliers(abortController.signal);
    } catch (err) {
        setStatusUpdateMessage(`Error updating status: ${err.message}`);
    } finally {
        setManualStatusUpdateInProgress(false);
    }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    setProcessing(true); setProcessError(null); setProcessSuccess(null); setStatusUpdateMessage('');
    if (!selectedSupplierId) { setProcessError("Please select a supplier."); setProcessing(false); return; }
    const weightFloat = parseFloat(shipmentWeight);
    if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Please enter a valid positive shipment weight."); setProcessing(false); return; }
     let itemValidationError = null;
     const currentPurchaseItems = purchaseItemsRef.current;
     const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
        const quantityInt = parseInt(item.quantity, 10);
        const costFloat = parseFloat(item.unit_cost);
        if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1} (SKU: ${item.sku || 'N/A'}) must have a quantity greater than 0.`; return null; }
        if (item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1} (SKU: ${item.sku || 'N/A'}) must have a valid unit cost.`; return null; }
        if (!item.sku) { itemValidationError = `Item #${index + 1} must have a Purchase SKU.`; return null; }
        if (!item.description) { itemValidationError = `Item #${index + 1} (SKU: ${item.sku}) must have a Description.`; return null; }
        return {
            original_order_line_item_id: item.original_order_line_item_id,
            sku: item.sku, description: item.description, quantity: quantityInt,
            unit_cost: costFloat.toFixed(2), condition: item.condition || 'New',
        };
     }).filter(item => item !== null);
    if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
    if (finalPurchaseItems.length === 0) { setProcessError("No valid line items for PO."); setProcessing(false); return; }
    const payload = {
      supplier_id: parseInt(selectedSupplierId, 10),
      payment_instructions: poNotes,
      total_shipment_weight_lbs: weightFloat,
      po_line_items: finalPurchaseItems,
    };
    const processApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/process`;
    try {
      const response = await fetch(processApiUrl, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      const responseData = await response.json().catch(() => null);
      if (!response.ok) { throw new Error(responseData?.details || responseData?.error || `HTTP error! Status: ${response.status}`); }
      setProcessSuccess(responseData.message || "Order processed successfully!");
      // Re-fetch after successful processing
      const abortController = new AbortController();
      await fetchOrderAndSuppliers(abortController.signal);
    } catch (err) {
      setProcessError(err.message || "An unexpected error occurred.");
    } finally {
      setProcessing(false);
    }
  };

  if (loading && !orderData) { // Show loading only if no data yet
    return <div className="loading-message">Loading order details...</div>;
  }
  if (error) {
    return <div className="error-message">Error loading data: {error}</div>;
  }
  if (!orderData || !orderData.order) {
    return <p>Order details not found.</p>;
  }

  const order = orderData.order;
  const originalLineItems = orderData.line_items || [];

  // Determine if the main "PROCESS ORDER" form and button should be disabled or hidden
  const isProcessed = order.status && typeof order.status === 'string' && order.status.toLowerCase() === 'processed';
  const isCompletedOffline = order.status && typeof order.status === 'string' && order.status.toLowerCase() === 'completed offline';
  
  // Condition to show the "PROCESS ORDER" button and related form elements
  const canProcessOrder = !(isProcessed || isCompletedOffline || 
                           (order.status && typeof order.status === 'string' && order.status.toLowerCase() === 'pending') ||
                           (order.status && typeof order.status === 'string' && order.status.toLowerCase() === 'international_manual'));

  const disableFormFields = isProcessed || isCompletedOffline || processing || manualStatusUpdateInProgress;


  let displayOrderDate = 'N/A';
  if (order.order_date && typeof order.order_date === 'string') {
    try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (dateError) {}
  }
  const displayCustomerShippingMethod = formatShippingMethod(order.customer_shipping_method);

  return (
    <div className="order-detail-container">
      <div className="order-title-section">
        <h2>
          <span>Order #{order.bigcommerce_order_id || 'N/A'} </span>
          <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order.bigcommerce_order_id)} className="copy-button" disabled={!order.bigcommerce_order_id}>📋</button>
          {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
        </h2>
        <span className={`order-status-badge status-${(order.status && typeof order.status === 'string' ? order.status.toLowerCase() : 'unknown').replace(/\s+/g, '-')}`}>
          {(order.status && typeof order.status === 'string' ? order.status : 'Unknown')}
        </span>
      </div>

      {/* Consolidated status messages */}
      {statusUpdateMessage && !processError && !processSuccess && (
          <div className={statusUpdateMessage.toLowerCase().includes("error") ? "error-message" : "success-message"} style={{marginTop: '10px', marginBottom: '10px'}}>
              {statusUpdateMessage}
          </div>
      )}
      {processSuccess && <div className="success-message" style={{ marginBottom: '10px' }}>{processSuccess}</div>}
      {processError && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}


      <section className="order-info card">
         <h3>Order Information</h3>
        <div><strong>Rec'd:</strong> {displayOrderDate}</div>
        <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
        <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
        <div><strong>Ship:</strong> {displayCustomerShippingMethod} to {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>
        {order.customer_notes && typeof order.customer_notes === 'string' && ( <div style={{marginTop: '5px'}}><strong>Comments:</strong> {order.customer_notes}</div> )}
        <hr style={{margin: '10px 0'}}/>
        {originalLineItems.map((item, index) => {
            let displaySalePrice = '0.00';
            if (item.sale_price !== null && item.sale_price !== undefined) {
                const parsedPrice = parseFloat(item.sale_price);
                if (!isNaN(parsedPrice)) displaySalePrice = parsedPrice.toFixed(2);
            }
            return (
                <div key={`orig-item-${item.line_item_id || index}`} className="order-info-item">
                    <span>({item.quantity || 0})</span>
                    <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.original_sku || ''}`} onClick={(e) => handleBrokerbinLinkClick(e, item.original_sku)}> {item.original_sku || 'N/A'} </a>
                    {item.hpe_option_pn && item.hpe_option_pn !== item.original_sku && ( <span> {' ('} <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.hpe_option_pn || ''}`} onClick={(e) => handleBrokerbinLinkClick(e, item.hpe_option_pn)}> {item.hpe_option_pn} </a> {')'} </span> )}
                     <span> @ ${displaySalePrice}</span>
                </div>
            );
        })}
      </section>

      {/* Manual Action Buttons - Placed above the main form */}
        <div className="manual-actions-section" style={{ marginTop: '20px', marginBottom: '0px', textAlign: 'center', display: 'flex', justifyContent: 'center', gap: '10px', flexWrap: 'wrap' }}>
            {order.status && (order.status.toLowerCase() === 'international_manual' || order.status.toLowerCase() === 'pending') && !isProcessed && !isCompletedOffline && (
                <button
                    onClick={() => handleManualStatusUpdate('Completed Offline')}
                    className="process-button manual-action-button"
                    disabled={manualStatusUpdateInProgress || processing}
                    style={{ backgroundColor: '#5cb85c', fontSize: '0.9em' }} // Green
                >
                    {manualStatusUpdateInProgress ? 'Updating...' : 'Mark as Completed Offline'}
                </button>
            )}
        </div>

      {canProcessOrder && (
          <form onSubmit={handleProcessOrder} className={`processing-form ${disableFormFields ? 'form-disabled' : ''}`}>
              <section className="purchase-info card">
                <h3>Purchase Information</h3>
                <div className="form-grid">
                  <label htmlFor="supplier">Supplier:</label>
                  <select id="supplier" value={selectedSupplierId} onChange={handleSupplierChange} required disabled={disableFormFields}><option value="">-- Select Supplier --</option>{(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name || 'Unnamed Supplier'}</option>))}</select>
                  <label htmlFor="poNotes">PO Notes:</label>
                  <textarea id="poNotes" value={poNotes} onChange={handlePoNotesChange} rows="3" disabled={disableFormFields}/>
                </div>
                <div className="purchase-items-grid">
                  <h4>Items to Purchase:</h4>
                   <div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                   {purchaseItems.map((item, index) => (
                      <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                          <div><label className="mobile-label" htmlFor={`sku-${index}`}>Purchase SKU:</label><input id={`sku-${index}`} type="text" value={item.sku || ''} onChange={(e) => handlePurchaseItemChange(index, 'sku', e.target.value)} placeholder="Purchase SKU" required disabled={disableFormFields} title={item.original_sku ? `Original: ${item.original_sku}`: ''} className="sku-input"/></div>
                          <div><label className="mobile-label" htmlFor={`desc-${index}`}>Description:</label><textarea id={`desc-${index}`} value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="PO Description" rows={2} disabled={disableFormFields} className="description-textarea"/></div>
                          <div className="qty-cost-row">
                              <div><label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label><input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableFormFields} className="qty-input"/></div>
                              <div><label className="mobile-label" htmlFor={`price-${index}`}>Cost:</label><input id={`price-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableFormFields} className="price-input"/></div>
                          </div>
                      </div>
                   ))}
                </div>
              </section>
              <section className="shipment-info card">
                    <h3>Shipment Information</h3>
                     <div className="form-grid">
                        <label htmlFor="shipmentMethod">Method:</label>
                        <select id="shipmentMethod" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableFormFields} required><option value="UPS Ground">UPS Ground</option><option value="UPS 2nd Day Air">UPS 2nd Day Air</option><option value="UPS Next Day Air">UPS Next Day Air</option></select>
                        <label htmlFor="shipmentWeight">Weight (lbs):</label>
                        <input type="number" id="shipmentWeight" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required disabled={disableFormFields} />
                    </div>
              </section>
              <div className="action-section">
                  <button type="submit" className="process-button" disabled={processing || manualStatusUpdateInProgress}>
                      {processing ? 'Processing...' : 'PROCESS ORDER'}
                  </button>
                  {/* "Process Manually (Set to Pending)" link for "New" orders */}
                  {order.status && order.status.toLowerCase() === 'new' && !isProcessed && !isCompletedOffline && (
                      <div style={{ marginTop: '10px', textAlign: 'center' }}>
                          <a
                              href="#"
                              onClick={(e) => {
                                  e.preventDefault();
                                  if (!manualStatusUpdateInProgress && !processing) {
                                      handleManualStatusUpdate('pending');
                                  }
                              }}
                              className="link-button" // Use existing link-button style or create new
                              style={{ fontSize: '0.9em', color: 'var(--text-secondary)' }}
                              disabled={manualStatusUpdateInProgress || processing}
                          >
                              {manualStatusUpdateInProgress ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                          </a>
                      </div>
                  )}
              </div>
          </form>
      )}

      {/* Show "Mark as Completed Offline" button if status is "Pending" or "International", and not already processed/completed offline */}
      {/* This button is now moved outside the main processing form and shown more prominently */}
      {order.status && (order.status.toLowerCase() === 'international_manual' || order.status.toLowerCase() === 'pending') && !isProcessed && !isCompletedOffline && (
          <div className="action-section" style={{marginTop: '15px', paddingTop: '15px', borderTop: '1px solid var(--border-light)'}}>
             {/* This button moved to .manual-actions-section above the form */}
          </div>
      )}

      {/* Fallback message if no actions are available */}
      {(isProcessed || isCompletedOffline) && !canProcessOrder && (
        <div style={{ textAlign: 'center', marginTop: '20px', color: 'var(--text-secondary)' }}>
            This order has been {order.status.toLowerCase()} and no further automated actions are available.
        </div>
      )}

    </div>
  );
}

export default OrderDetail;
// --- END OF FILE OrderDetail.jsx ---