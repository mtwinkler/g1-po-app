// OrderDetail.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import './OrderDetail.css';
import { useAuth } from '../contexts/AuthContext';
// pdfIconUrl import is removed as it's no longer used

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

const createBrokerbinLink = (partNumber) => {
  if (!partNumber) return '#';
  const trimmedPartNumber = String(partNumber).trim();
  if (!trimmedPartNumber) return '#';
  const encodedPartNumber = encodeURIComponent(trimmedPartNumber);
  return `https://members.brokerbin.com/partkey?login=g1tech&parts=${encodedPartNumber}`;
};

function escapeRegExp(string) {
  if (typeof string !== 'string') return '';
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const formatShippingMethod = (methodString) => {
  if (!methodString || typeof methodString !== 'string') {
    return 'N/A'; 
  }
  const match = methodString.match(/\(([^)]+)\)/);
  if (match && match[1]) {
    const extracted = match[1].trim();
    const lowerExtracted = extracted.toLowerCase();
    if (lowerExtracted.includes('ups ground')) return 'UPS Ground';
    if (lowerExtracted.includes('ups 2nd day air') || lowerExtracted.includes('ups second day air')) return 'UPS 2nd Day Air';
    if (lowerExtracted.includes('ups next day air early a.m.') || lowerExtracted.includes('ups next day air e')) return 'UPS Next Day Air Early A.M.';
    if (lowerExtracted.includes('ups next day air')) return 'UPS Next Day Air';
    return extracted;
  }
  const lowerMethodString = methodString.toLowerCase();
  if (lowerMethodString.includes('ground')) return 'UPS Ground';
  if (lowerMethodString.includes('2nd day') || lowerMethodString.includes('second day')) return 'UPS 2nd Day Air';
  if (lowerMethodString.includes('next day air early a.m.') || lowerMethodString.includes('next day air e')) return 'UPS Next Day Air Early A.M.';
  if (lowerMethodString.includes('next day') || lowerMethodString.includes('nda')) return 'UPS Next Day Air';
  if (lowerMethodString.includes('free shipping')) return 'UPS Ground'; // Added based on common practice
  return String(methodString).trim();
};

const MULTI_SUPPLIER_MODE_VALUE = "_MULTI_SUPPLIER_MODE_";
const SHIPPING_METHODS_OPTIONS = [
    { value: "UPS Ground", label: "UPS Ground" },
    { value: "UPS 2nd Day Air", label: "UPS 2nd Day Air" },
    { value: "UPS Next Day Air", label: "UPS Next Day Air" },
    { value: "UPS Next Day Air Early A.M.", label: "UPS Next Day Air Early A.M." }
];

function OrderDetail() {
  const { orderId } = useParams();
  const { currentUser, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const VITE_API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

  const [orderData, setOrderData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(false); 
  const [processSuccessMessage, setProcessSuccessMessage] = useState(''); 
  const [processedPOsInfo, setProcessedPOsInfo] = useState([]); 
  const [processError, setProcessError] = useState(null);
  const [clipboardStatus, setClipboardStatus] = useState('');
  const [statusUpdateMessage, setStatusUpdateMessage] = useState('');
  const [manualStatusUpdateInProgress, setManualStatusUpdateInProgress] = useState(false);

  const [purchaseItems, setPurchaseItems] = useState([]);
  const [shipmentMethod, setShipmentMethod] = useState('UPS Ground');
  const [shipmentWeight, setShipmentWeight] = useState('');

  const [selectedMainSupplierTrigger, setSelectedMainSupplierTrigger] = useState('');
  const [isMultiSupplierMode, setIsMultiSupplierMode] = useState(false);
  const [singleOrderPoNotes, setSingleOrderPoNotes] = useState('');
  const [lineItemAssignments, setLineItemAssignments] = useState({});
  const [poNotesBySupplier, setPoNotesBySupplier] = useState({});
  const [multiSupplierItemCosts, setMultiSupplierItemCosts] = useState({});
  const [multiSupplierItemDescriptions, setMultiSupplierItemDescriptions] = useState({});
  const [multiSupplierShipmentDetails, setMultiSupplierShipmentDetails] = useState({});
  const [originalCustomerShippingMethod, setOriginalCustomerShippingMethod] = useState('UPS Ground');

  const [lineItemSpares, setLineItemSpares] = useState({});
  const [loadingSpares, setLoadingSpares] = useState(false);

  const setPurchaseItemsRef = useRef(setPurchaseItems);
  useEffect(() => { setPurchaseItemsRef.current = setPurchaseItems; }, []);
  const purchaseItemsRef = useRef(purchaseItems);
  useEffect(() => { purchaseItemsRef.current = purchaseItems; }, [purchaseItems]);

  const cleanPullSuffix = " - clean pull";

  const fetchOrderAndSuppliers = useCallback(async (signal, isPostProcessRefresh = false) => {
    if (!currentUser) {
        setLoading(false); setOrderData(null); setSuppliers([]); return;
    }
    setLoading(true); setError(null); 
    
    if (!isPostProcessRefresh) {
        setProcessSuccess(false); 
        setProcessSuccessMessage(''); 
        setProcessedPOsInfo([]); 
        setProcessError(null); 
    }
    setStatusUpdateMessage('');

    try {
        const token = await currentUser.getIdToken(true);
        const headers = { 'Authorization': `Bearer ${token}` };
        const orderApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}`;
        const suppliersApiUrl = `${VITE_API_BASE_URL}/suppliers`; 
        const [orderResponse, suppliersResponse] = await Promise.all([
            fetch(orderApiUrl, { signal, headers }),
            fetch(suppliersApiUrl, { signal, headers })
        ]);
        if (signal?.aborted) return;
        if (!orderResponse.ok) throw new Error(`Order fetch failed: ${orderResponse.statusText} (${orderResponse.status})`);
        if (!suppliersResponse.ok) throw new Error(`Supplier fetch failed: ${suppliersResponse.statusText} (${suppliersResponse.status})`);
        const fetchedOrderData = await orderResponse.json();
        const fetchedSuppliers = await suppliersResponse.json();
        if (signal?.aborted) return;

        setOrderData(fetchedOrderData);
        setSuppliers(fetchedSuppliers || []); 
        
        if (!isPostProcessRefresh) {
            setLineItemSpares({});
            setMultiSupplierItemCosts({});
            setMultiSupplierItemDescriptions({});
            setMultiSupplierShipmentDetails({});

            if (fetchedOrderData?.order) {
                const customerMethodRaw = fetchedOrderData.order.customer_shipping_method;
                const parsedCustomerMethod = formatShippingMethod(customerMethodRaw);
                const validShippingOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedCustomerMethod);
                const finalCustomerMethod = validShippingOption ? parsedCustomerMethod : 'UPS Ground';
                setShipmentMethod(finalCustomerMethod);
                setOriginalCustomerShippingMethod(finalCustomerMethod); 
            }
            if (fetchedOrderData?.line_items) {
                const initialItems = fetchedOrderData.line_items.map(item => ({
                    original_order_line_item_id: item.line_item_id,
                    sku: item.hpe_option_pn || item.original_sku || '',
                    description: (item.hpe_po_description || item.line_item_name || '') + ( (item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
                    skuInputValue: item.hpe_option_pn || item.original_sku || '',
                    quantity: item.quantity || 1,
                    unit_cost: '',
                    condition: 'New',
                    original_sku: item.original_sku,
                    hpe_option_pn: item.hpe_option_pn,
                    original_name: item.line_item_name,
                    hpe_po_description: item.hpe_po_description,
                    hpe_pn_type: item.hpe_pn_type,
                }));
                setPurchaseItemsRef.current(initialItems);

                const initialMultiDesc = {};
                fetchedOrderData.line_items.forEach(item => {
                    let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                    if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) {
                        defaultDescription += cleanPullSuffix;
                    } else if (!defaultDescription && item.original_sku) {
                         defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
                    }
                    initialMultiDesc[item.line_item_id] = defaultDescription;
                });
                setMultiSupplierItemDescriptions(initialMultiDesc);
            } else {
                setPurchaseItemsRef.current([]);
                setMultiSupplierItemDescriptions({});
            }
        } else if (fetchedOrderData?.order) { 
            setOriginalCustomerShippingMethod(formatShippingMethod(fetchedOrderData.order.customer_shipping_method) || 'UPS Ground');
        }

    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message || "An unknown error occurred.");
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, cleanPullSuffix, VITE_API_BASE_URL, currentUser]);

  useEffect(() => {
    if (authLoading) { setLoading(true); return; }
    const abortController = new AbortController();
    if (orderId && currentUser) {
        fetchOrderAndSuppliers(abortController.signal, false);
    }
    else if (!currentUser && orderId) { setLoading(false); setError("Please log in."); }
    else if (!orderId) { setError("Order ID missing."); setLoading(false); }
    return () => abortController.abort();
  }, [orderId, currentUser, authLoading, fetchOrderAndSuppliers]);

  useEffect(() => {
    if (!currentUser || !orderData?.line_items || orderData.line_items.length === 0) return;
    const fetchAllSpares = async () => {
        setLoadingSpares(true);
        const sparesMap = {};
        const token = await currentUser.getIdToken(true);
        for (const item of orderData.line_items) {
            if (item.original_sku && item.hpe_pn_type === 'option') {
                try {
                    const trimmedOriginalSku = String(item.original_sku).trim();
                    if (!trimmedOriginalSku) continue;
                    const spareApiUrl = `${VITE_API_BASE_URL}/lookup/spare_part/${encodeURIComponent(trimmedOriginalSku)}`;
                    const response = await fetch(spareApiUrl, { headers: { 'Authorization': `Bearer ${token}` } });
                    if (response.ok) {
                        const spareData = await response.json();
                        if (spareData.spare_sku) sparesMap[item.line_item_id] = String(spareData.spare_sku).trim();
                    } else if (response.status !== 404) console.error(`Spare lookup error for ${trimmedOriginalSku}: ${response.status}`);
                } catch (err) { console.error(`Spare lookup exception for ${item.original_sku}:`, err); }
            }
        }
        setLineItemSpares(sparesMap); setLoadingSpares(false);
    };
    fetchAllSpares();
  }, [orderData?.line_items, currentUser, VITE_API_BASE_URL]);

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);
  useEffect(() => {
    if (!currentUser || !debouncedSku || skuToLookup.index === -1 || isMultiSupplierMode) return;
    const abortController = new AbortController();
    const fetchDescription = async () => {
      try {
        const token = await currentUser.getIdToken(true);
        const lookupApiUrl = `${VITE_API_BASE_URL}/lookup/description/${encodeURIComponent(String(debouncedSku).trim())}`;
        const response = await fetch(lookupApiUrl, { signal: abortController.signal, headers: { 'Authorization': `Bearer ${token}` } });
        if (abortController.signal.aborted) return;
        if (response.ok) {
            const data = await response.json();
            if (abortController.signal.aborted) return;
            const currentItems = purchaseItemsRef.current;
            const updatedItems = [...currentItems];
            if (updatedItems[skuToLookup.index]?.skuInputValue === debouncedSku) { // Check if the input value hasn't changed
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) newDescription += cleanPullSuffix;
                else if (!newDescription) { // if API returns no description, append suffix to existing or just use suffix
                    const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDesc ? existingDesc + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) newDescription = cleanPullSuffix.trim(); // Avoid leading space if existingDesc was empty
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
                setPurchaseItemsRef.current(updatedItems);
            }
        } else if (response.status === 401 || response.status === 403) {
            console.error("Unauthorized to fetch SKU description.");
            // Optionally: navigate('/login') or show user message
        }
        // No specific error handling for 404, as it just means no description found.
      } catch (error) { if (error.name !== 'AbortError') console.error("Error fetching description:", error); }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, VITE_API_BASE_URL, currentUser, isMultiSupplierMode]); // isMultiSupplierMode added to dependencies
  
  const handleMainSupplierTriggerChange = (e) => {
    const value = e.target.value;
    setSelectedMainSupplierTrigger(value);
    setProcessError(null); 
    setProcessSuccess(false); 
    setProcessSuccessMessage(''); 
    setProcessedPOsInfo([]);
    if (value === MULTI_SUPPLIER_MODE_VALUE) {
        setIsMultiSupplierMode(true);
        setSingleOrderPoNotes('');
        // Reset single supplier fields
        setShipmentMethod(originalCustomerShippingMethod); // Reset to original customer method
        setShipmentWeight('');
        // Initialize multi-supplier specific states
        setLineItemAssignments({});
        setPoNotesBySupplier({});
        setMultiSupplierItemCosts({});
        // Re-initialize multi-supplier descriptions based on current order data
        const initialMultiDesc = {};
        if (orderData?.line_items) {
            orderData.line_items.forEach(item => {
                let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) {
                    defaultDescription += cleanPullSuffix;
                } else if (!defaultDescription && item.original_sku) {
                     defaultDescription = `${item.original_sku}${cleanPullSuffix}`; // Fallback to SKU + suffix
                }
                initialMultiDesc[item.line_item_id] = defaultDescription;
            });
        }
        setMultiSupplierItemDescriptions(initialMultiDesc);
        setMultiSupplierShipmentDetails({}); // Clear previous multi-supplier shipment details
    } else { // Single supplier mode or no supplier selected
        setIsMultiSupplierMode(false);
        const s = suppliers.find(sup => sup.id === parseInt(value, 10));
        setSingleOrderPoNotes(s?.defaultponotes || '');
        setShipmentMethod(originalCustomerShippingMethod); // Reset to original
        // Clear multi-supplier states
        setLineItemAssignments({});
        setPoNotesBySupplier({});
        setMultiSupplierItemCosts({});
        setMultiSupplierItemDescriptions({});
        setMultiSupplierShipmentDetails({});
    }
  };
  const handleSingleOrderPoNotesChange = (e) => setSingleOrderPoNotes(e.target.value);
  const handleLineItemSupplierAssignment = (originalLineItemId, supplierId) => {
    setLineItemAssignments(prev => ({ ...prev, [originalLineItemId]: supplierId }));
    // If a supplier is assigned and their PO notes aren't set yet, set default notes
    if (supplierId && !poNotesBySupplier[supplierId]) {
        const s = suppliers.find(sup => sup.id === parseInt(supplierId, 10));
        setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: s?.defaultponotes || '' }));
    }
    // If a supplier is assigned in multi-supplier mode and shipment details aren't set, initialize them
    if (supplierId && isMultiSupplierMode && !multiSupplierShipmentDetails[supplierId]) {
        setMultiSupplierShipmentDetails(prev => ({
            ...prev,
            [supplierId]: { method: originalCustomerShippingMethod, weight: '' } // Default to customer's method
        }));
    }
  };
  const handlePoNotesBySupplierChange = (supplierId, notes) => {
    setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: notes }));
  };
  const handleMultiSupplierItemCostChange = (originalLineItemId, cost) => {
    setMultiSupplierItemCosts(prev => ({ ...prev, [originalLineItemId]: cost }));
  };
  const handleMultiSupplierItemDescriptionChange = (originalLineItemId, description) => {
    setMultiSupplierItemDescriptions(prev => ({ ...prev, [originalLineItemId]: description }));
  };
  const handleMultiSupplierShipmentDetailChange = (supplierId, field, value) => {
    setMultiSupplierShipmentDetails(prev => ({
        ...prev,
        [supplierId]: {
            ...(prev[supplierId] || { method: originalCustomerShippingMethod, weight: '' }), // Default if not existing
            [field]: value
        }
    }));
  };
  const handlePurchaseItemChange = (index, field, value) => {
    const items = [...purchaseItemsRef.current];
    items[index] = { ...items[index], [field]: value };
    if (field === 'sku') {
        const trimmedSku = String(value).trim();
        items[index].sku = trimmedSku; // Update the actual SKU for submission
        items[index].skuInputValue = trimmedSku; // Keep input value separate for debouncing
        setSkuToLookup({ index, sku: trimmedSku });
    }
    setPurchaseItemsRef.current(items);
  };
  const handleShipmentMethodChange = (e) => setShipmentMethod(e.target.value);
  const handleShipmentWeightChange = (e) => setShipmentWeight(e.target.value);
  const handleCopyToClipboard = async (textToCopy) => {
    if (!textToCopy) return;
    try {
        await navigator.clipboard.writeText(String(textToCopy).trim());
        setClipboardStatus(`Copied: ${String(textToCopy).trim()}`);
        setTimeout(() => setClipboardStatus(''), 1500);
    } catch (err) {
        console.error('Clipboard write failed:', err);
        setClipboardStatus('Failed to copy!');
        setTimeout(() => setClipboardStatus(''), 1500);
    }
  };

  // NEW FUNCTION to handle part number link clicks
  const handlePartNumberLinkClick = async (e, partNumber) => {
    e.preventDefault(); // Prevent default link navigation to control the flow

    // 1. Copy Order# to clipboard
    if (orderData?.order?.bigcommerce_order_id) {
        await handleCopyToClipboard(orderData.order.bigcommerce_order_id);
    }

    // 2. Perform original status update logic (adapted from former handleBrokerbinLinkClick)
    if (!currentUser) {
        setStatusUpdateMessage("Please log in to perform this action.");
        // Do not proceed to open link if not logged in
        return; 
    }
    
    const currentOrderStatus = orderData?.order?.status?.toLowerCase();
    const trimmedPartNumberForStatusCheck = String(partNumber || '').trim();

    // Only attempt status update if order status is 'new' and there's a part number
    if (currentOrderStatus === 'new' && trimmedPartNumberForStatusCheck) {
      try {
        // Clear message only if attempting an update, otherwise preserve existing messages
        setStatusUpdateMessage(''); 
        const token = await currentUser.getIdToken(true);
        const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
        const response = await fetch(statusApiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ status: 'RFQ Sent' })
        });
        const responseData = await response.json().catch(() => null);
        if (!response.ok) {
            let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`;
            if (response.status === 401 || response.status === 403) {
                err = "Unauthorized. Please log in again.";
                navigate('/login'); // Redirect if session is invalid
            }
            throw new Error(err);
        }
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, false); // Refresh order data to reflect new status
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${trimmedPartNumberForStatusCheck}`);
      } catch (err) {
        setStatusUpdateMessage(`Error updating status for part ${trimmedPartNumberForStatusCheck}: ${err.message}`);
      }
    } else if (trimmedPartNumberForStatusCheck && currentOrderStatus && !['new', 'rfq sent', 'processed', 'completed offline', 'pending'].includes(currentOrderStatus)) {
      // If status is not 'new' and a part number was clicked, inform user status wasn't changed.
      // Avoid clearing other important messages like "Order Processed Successfully".
      // This message is less critical than error or success messages.
      // setStatusUpdateMessage(`Order status is '${orderData?.order?.status}'. Part status not updated.`);
    }
    // If no status update logic was triggered, existing statusUpdateMessage (if any) will persist.

    // 3. Open Brokerbin URL in a new window
    const brokerbinUrl = createBrokerbinLink(partNumber);
    window.open(brokerbinUrl, '_blank', 'noopener,noreferrer');
  };

  // REMOVE or comment out the old handleBrokerbinLinkClick function:
  /*
  const handleBrokerbinLinkClick = async (e, partNumber) => {
    // ... old code ...
  };
  */

  const handleManualStatusUpdate = async (newStatus) => {
    if (!currentUser) { setStatusUpdateMessage("Please log in to update status."); return; }
    if (!orderId || !VITE_API_BASE_URL) { setStatusUpdateMessage("Configuration error."); return; } // Basic check
    setManualStatusUpdateInProgress(true); setStatusUpdateMessage(''); // Clear message before action
    try {
        const token = await currentUser.getIdToken(true);
        const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
        const response = await fetch(statusApiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ status: newStatus }) });
        const responseData = await response.json().catch(() => null); // Gracefully handle non-JSON response
        if (!response.ok) { let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`; if(response.status===401||response.status===403) {err="Unauthorized. Please log in again."; navigate('/login');} throw new Error(err); }
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal, false); // Refresh data
    } catch (err) { setStatusUpdateMessage(`Error updating status: ${err.message}`);
    } finally { setManualStatusUpdateInProgress(false); }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    if (!currentUser) { setProcessError("Please log in."); return; }
    setProcessing(true); setProcessError(null); setProcessSuccess(false); setProcessSuccessMessage(''); setProcessedPOsInfo([]); setStatusUpdateMessage('');

    let payloadAssignments = [];
    const currentOriginalLineItems = orderData?.line_items || [];

    if (isMultiSupplierMode) {
        const assignedSupplierIds = [...new Set(Object.values(lineItemAssignments))].filter(id => id); // Get unique, non-empty supplier IDs
        
        // Check if any items exist to be assigned
        if (currentOriginalLineItems.length > 0) {
            if (assignedSupplierIds.length === 0) {
                setProcessError("Multi-Supplier Mode: Assign items to at least one supplier.");
                setProcessing(false); return;
            }
            // Check if all original items are assigned
            const allOriginalItemsAssigned = currentOriginalLineItems.every(item => !!lineItemAssignments[item.line_item_id]);
            if (!allOriginalItemsAssigned) {
                setProcessError("Multi-Supplier Mode: Assign all original items to a supplier.");
                setProcessing(false); return;
            }
        }


        for (const supId of assignedSupplierIds) {
            const itemsForThisSupplier = currentOriginalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supId);
            if (itemsForThisSupplier.length > 0) {
                let itemCostValidationError = null;
                const poLineItems = itemsForThisSupplier.map(item => {
                    const costStr = multiSupplierItemCosts[item.line_item_id];
                    const costFloat = parseFloat(costStr);
                    if (costStr === undefined || costStr === '' || isNaN(costFloat) || costFloat < 0) {
                        itemCostValidationError = `Missing or invalid unit cost for SKU ${item.original_sku || 'N/A'} (Supplier: ${suppliers.find(s=>s.id===parseInt(supId,10))?.name}).`;
                        return null; // Invalid item, will be filtered out
                    }
                    let descriptionForPo = multiSupplierItemDescriptions[item.line_item_id];
                    if (descriptionForPo === undefined) { // Fallback if not set
                        descriptionForPo = item.hpe_po_description || item.line_item_name || `${item.original_sku || ''}${cleanPullSuffix}`;
                    }
                    if (!String(descriptionForPo).trim()) {
                        itemCostValidationError = `Missing description for SKU ${item.original_sku || 'N/A'} (Supplier: ${suppliers.find(s=>s.id===parseInt(supId,10))?.name}).`;
                        return null;
                    }
                    return {
                        original_order_line_item_id: item.line_item_id,
                        sku: item.hpe_option_pn || item.original_sku, // Prefer HPE Option PN if available
                        description: String(descriptionForPo).trim(),
                        quantity: item.quantity,
                        unit_cost: costFloat.toFixed(2),
                        condition: 'New', // Assuming 'New' condition
                    };
                }).filter(Boolean); // Remove nulls from validation errors

                if (itemCostValidationError) { setProcessError(itemCostValidationError); setProcessing(false); return; }
                // This check might be redundant if itemCostValidationError is comprehensive
                if (poLineItems.length !== itemsForThisSupplier.length && itemsForThisSupplier.length > 0) {
                    setProcessError("One or more items for a supplier had validation errors (e.g., missing cost/description)."); 
                    setProcessing(false); return; 
                }
                
                const shipmentDetailsForThisPo = multiSupplierShipmentDetails[supId] || {};
                const currentPoWeight = shipmentDetailsForThisPo.weight;
                const currentPoMethod = shipmentDetailsForThisPo.method;

                // Validate weight only if a shipping method is selected
                if (currentPoMethod && (!currentPoWeight || parseFloat(currentPoWeight) <= 0)) {
                    setProcessError(`Invalid/missing weight for PO to ${suppliers.find(s=>s.id === parseInt(supId, 10))?.name} when a shipping method is selected.`);
                    setProcessing(false); return;
                }
                // Validate method only if weight is entered (implies shipping)
                if (!currentPoMethod && currentPoWeight && parseFloat(currentPoWeight) > 0) {
                    setProcessError(`Shipping method required for PO to ${suppliers.find(s=>s.id === parseInt(supId, 10))?.name} when weight is provided.`);
                    setProcessing(false); return;
                }
                
                payloadAssignments.push({
                    supplier_id: parseInt(supId, 10),
                    payment_instructions: poNotesBySupplier[supId] || "",
                    po_line_items: poLineItems,
                    total_shipment_weight_lbs: currentPoWeight ? parseFloat(currentPoWeight).toFixed(1) : null,
                    shipment_method: currentPoMethod || null // Send null if no method selected
                });
            }
        }
        // Ensure there are assignments only if there were items to begin with
        if (payloadAssignments.length === 0 && currentOriginalLineItems.length > 0) {
             setProcessError("No items were successfully assigned or configured for PO generation.");
             setProcessing(false); return;
        }
    } else { // Single Supplier Mode
        const singleSelectedSupId = selectedMainSupplierTrigger;
        if (!singleSelectedSupId || singleSelectedSupId === MULTI_SUPPLIER_MODE_VALUE) {
            setProcessError("Please select a supplier."); setProcessing(false); return;
        }
        // Only require weight and method if there are items to process
        if (currentOriginalLineItems.length > 0) {
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight."); setProcessing(false); return; }
            if (!shipmentMethod) { setProcessError("Please select a shipment method."); setProcessing(false); return; }
        }

        let itemValidationError = null;
        const finalPurchaseItems = purchaseItemsRef.current.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10); const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1}: Quantity must be > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1}: Unit cost is invalid.`; return null; }
            if (!String(item.sku).trim()) { itemValidationError = `Item #${index + 1}: SKU is required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `Item #${index + 1}: Description is required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.sku).trim(), description: String(item.description).trim(), quantity: quantityInt, unit_cost: costFloat.toFixed(2), condition: item.condition || 'New' };
        }).filter(Boolean);

        if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
        // This condition allows processing even if original order had no items (e.g. manual PO)
        if (finalPurchaseItems.length === 0 && currentOriginalLineItems.length > 0) { 
            setProcessError("No valid line items for PO. Please check quantities, costs, SKUs, and descriptions."); 
            setProcessing(false); return; 
        }
        
        // Add to payload if there are items, or if it's a manual PO (no original items but user might have added some - though current UI doesn't support adding new items from scratch)
        // The key is that finalPurchaseItems could be empty if the original order had no items.
        // If original order had items, finalPurchaseItems must not be empty.
        // If original order had no items, finalPurchaseItems will also be empty, and that's OK for a zero-item PO if allowed by backend.
        // For now, assuming a PO needs items if the original order had items.
        if (finalPurchaseItems.length > 0 || currentOriginalLineItems.length === 0) {
             payloadAssignments.push({
                supplier_id: parseInt(singleSelectedSupId, 10),
                payment_instructions: singleOrderPoNotes,
                total_shipment_weight_lbs: (currentOriginalLineItems.length > 0 || finalPurchaseItems.length > 0) ? parseFloat(shipmentWeight).toFixed(1) : null, // Only send weight if items
                shipment_method: (currentOriginalLineItems.length > 0 || finalPurchaseItems.length > 0) ? shipmentMethod : null, // Only send method if items
                po_line_items: finalPurchaseItems
            });
        }
    }
    
    // Final check on payloadAssignments
    // If original order had items, then payloadAssignments should not be empty.
    if (payloadAssignments.length === 0 && currentOriginalLineItems.length > 0 ) {
        setProcessError("No data to create Purchase Orders. Check item assignments and details.");
        setProcessing(false); return;
    }
    
    try {
        const token = await currentUser.getIdToken(true);
        const finalPayload = { assignments: payloadAssignments };
        const processApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/process`;
        const response = await fetch(processApiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify(finalPayload) });
        const responseData = await response.json().catch(() => ({ message: "Processing request sent, but response was not valid JSON." })); 
        
        if (!response.ok) { 
            let err = responseData?.details || responseData?.error || responseData?.message || `HTTP error ${response.status}`; 
            if (response.status === 401 || response.status === 403) { err = "Unauthorized. Please log in again."; navigate('/login'); } 
            throw new Error(err); 
        }
        
        setProcessSuccess(true); 
        setProcessSuccessMessage(responseData.message || "Order processed successfully!"); 
        setProcessedPOsInfo(Array.isArray(responseData.processed_purchase_orders) ? responseData.processed_purchase_orders : []); 
        
        const ac = new AbortController(); 
        await fetchOrderAndSuppliers(ac.signal, true); // Refresh order data post-processing
    } catch (err) {
        setProcessError(err.message || "An unexpected error occurred during processing.");
        setProcessSuccess(false); // Ensure success is false on error
        setProcessedPOsInfo([]); // Clear any PO info on error
    } finally {
        setProcessing(false);
    }
  };


  // ... (rest of the component, including the return statement)
  // WITHIN the return statement, update the links:

  // For item.original_sku:
  // <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.original_sku}`} onClick={(e) => handleBrokerbinLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>
  // BECOMES:
  // <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.original_sku}`} onClick={(e) => handlePartNumberLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>

  // For lineItemSpares[item.line_item_id]:
  // <a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handleBrokerbinLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a>
  // BECOMES:
  // <a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handlePartNumberLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a>

  // For item.hpe_option_pn:
  // <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handleBrokerbinLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a>
  // BECOMES:
  // <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handlePartNumberLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a>


  if (authLoading) return <div className="loading-message">Loading session...</div>;
  if (!currentUser) return <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}><h2>Order Details</h2><p className="error-message">Please <Link to="/login">log in</Link>.</p></div>;
  // Show loading only if not already showing process success and orderData is not yet loaded.
  if (loading && !orderData && !processSuccess) return <div className="loading-message">Loading order details...</div>; 
  if (error) return <div className="error-message">Error: {error}</div>;
  
  const order = orderData?.order; // Use optional chaining for safety
  const originalLineItems = orderData?.line_items || [];

  // If not processing successfully and order details are still missing, show not found.
  if (!order && !processSuccess) { 
      return <p style={{ textAlign: 'center', marginTop: '20px' }}>Order details not found or error loading.</p>;
  }

  const isActuallyProcessed = order?.status?.toLowerCase() === 'processed';
  const isActuallyCompletedOffline = order?.status?.toLowerCase() === 'completed offline';
  // Display processing form if not showing a new success message AND order isn't already processed/completed.
  const canDisplayProcessingForm = !processSuccess && !(isActuallyProcessed || isActuallyCompletedOffline);
  const disableAllActions = processing || manualStatusUpdateInProgress;
  // Disable form fields if already processed/completed, or general actions disabled, or new success message shown.
  const disableEditableFormFields = isActuallyProcessed || isActuallyCompletedOffline || disableAllActions || processSuccess;


  let displayOrderDate = 'N/A';
  if (order?.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) { /* ignore date parsing error */ }
  const displayCustomerShippingMethod = formatShippingMethod(order?.customer_shipping_method);

  return (
    <div className="order-detail-container">
      <div className="order-title-section">
        <h2>
          <span>Order #{order?.bigcommerce_order_id || orderId} </span>
          <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order?.bigcommerce_order_id)} className="copy-button" disabled={!order?.bigcommerce_order_id}>📋</button>
          {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
        </h2>
        {order && ( // Only show status if order object exists
            <span className={`order-status-badge status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
            {order.status || 'Unknown'}
            </span>
        )}
      </div>

      {/* Prioritize processError and processSuccess messages over statusUpdateMessage */}
      {statusUpdateMessage && !processError && !processSuccess && (
          <div className={statusUpdateMessage.toLowerCase().includes("error") ? "error-message" : "success-message"} style={{ marginTop: '10px', marginBottom: '10px' }}>
              {statusUpdateMessage}
          </div>
      )}

      {processError && <div className="error-message" style={{ marginBottom: '10px' }}>{processError}</div>}

      {processSuccess && (
        <div className="process-success-container card">
          <p className="success-message-large">ORDER PROCESSED SUCCESSFULLY!</p>
          {processSuccessMessage && processSuccessMessage !== "Order processed successfully!" && (
            <p className="success-message-detail">{processSuccessMessage}</p>
          )}
          {Array.isArray(processedPOsInfo) && processedPOsInfo.length > 0 && (
            <div className="processed-po-links">
              <h4>Generated Documents:</h4>
              {processedPOsInfo.map((poInfo, index) => {
                const supplierForPO = suppliers.find(s => s.id === poInfo.supplier_id);
                const supplierName = supplierForPO ? supplierForPO.name : `ID: ${poInfo.supplier_id}`;
                const poTitle = `PO #${poInfo.po_number} sent to ${supplierName}`;
                
                const hasAnyPdf = poInfo.po_pdf_gcs_uri || poInfo.packing_slip_gcs_uri || poInfo.label_gcs_uri;

                return (
                    <div key={poInfo.po_number || index} className="po-document-group">
                        <p className="po-number-title">{poTitle}</p>
                        {hasAnyPdf ? (
                            <div className="pdf-links-wrapper">
                                {poInfo.po_pdf_gcs_uri && (
                                    <a href={poInfo.po_pdf_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link">
                                    {/* Removed img tag for pdfIconUrl as it's not defined */}
                                     View PO
                                    </a>
                                )}
                                {poInfo.packing_slip_gcs_uri && (
                                    <a href={poInfo.packing_slip_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link">
                                     View Packing Slip
                                    </a>
                                )}
                                {poInfo.label_gcs_uri && (
                                    <a href={poInfo.label_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link">
                                     View Label
                                    </a>
                                )}
                            </div>
                        ) : (
                            <p className="no-documents-note">No PDF document links available for this PO.</p>
                        )}
                    </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Display Order Information only if not showing the success message AND orderData/order exists */}
      {orderData && order && !processSuccess && (
       <section className="order-info card">
        <h3>Order Information</h3>
        <div><strong>Rec'd:</strong> {displayOrderDate}</div>
        <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
        <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
        <div><strong>Ship:</strong> {displayCustomerShippingMethod} to {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>
        {order.customer_notes && (<div style={{ marginTop: '5px' }}><strong>Comments:</strong> {order.customer_notes}</div>)}
        <hr style={{ margin: '10px 0' }} />
        {originalLineItems.map((item) => (
            <p key={`orig-item-${item.line_item_id}`} className="order-info-sku-line">
                <span>({item.quantity || 0}) </span>
                {/* MODIFIED LINK BELOW */}
                <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.original_sku}`} onClick={(e) => handlePartNumberLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>
                
                {loadingSpares && item.hpe_pn_type === 'option' && !lineItemSpares[item.line_item_id] && <span className="loading-text"> (loading spare...)</span>}
                
                {lineItemSpares[item.line_item_id] && (
                    <span style={{ fontStyle: 'italic', marginLeft: '5px' }}>(
                        {/* MODIFIED LINK BELOW */}
                        <a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handlePartNumberLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a>
                    )</span>
                )}
                
                {item.hpe_option_pn && String(item.hpe_option_pn).trim() !== String(item.original_sku).trim() && String(item.hpe_option_pn).trim() !== lineItemSpares[item.line_item_id] && (
                    <span>{' ('}
                        {/* MODIFIED LINK BELOW */}
                        <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handlePartNumberLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a>
                    {')'}</span>
                )}
                <span> @ ${parseFloat(item.sale_price || 0).toFixed(2)}</span>
            </p>
        ))}
      </section>
      )}

     {canDisplayProcessingForm && (
        <section className="supplier-mode-selection card">
        <h3>Begin Order Fulfillment</h3>
        <div className="form-grid">
            <label htmlFor="mainSupplierTrigger"></label> {/* Consider adding "Select Supplier Mode:" or similar text */}
            <select id="mainSupplierTrigger" value={selectedMainSupplierTrigger} onChange={handleMainSupplierTriggerChange} disabled={disableAllActions || suppliers.length === 0}>
                <option value="">-- Select Supplier --</option>
                <option value={MULTI_SUPPLIER_MODE_VALUE}>** Use Multiple Suppliers **</option>
                {(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name || 'Unnamed Supplier'}</option>))}
            </select>
        </div>
      </section>
     )}

      {canDisplayProcessingForm && !isMultiSupplierMode && selectedMainSupplierTrigger && selectedMainSupplierTrigger !== MULTI_SUPPLIER_MODE_VALUE && (
        <form onSubmit={handleProcessOrder} className={`processing-form ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="purchase-info card">
              <h3>Create PO for {suppliers.find(s=>s.id === parseInt(selectedMainSupplierTrigger, 10))?.name || ''}</h3>
              <div className="form-grid">
                <label htmlFor="singlePoNotes">PO Notes:</label>
                <textarea id="singlePoNotes" value={singleOrderPoNotes} onChange={handleSingleOrderPoNotesChange} rows="3" disabled={disableEditableFormFields} />
              </div>
              <div className="purchase-items-grid">
                <h4>Items to Purchase:</h4>
                <div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                {purchaseItems.map((item, index) => ( 
                     <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                        <div><label className="mobile-label" htmlFor={`sku-${index}`}>SKU:</label><input id={`sku-${index}`} type="text" value={item.skuInputValue || ''} onChange={(e) => handlePurchaseItemChange(index, 'sku', e.target.value)} placeholder="SKU" required disabled={disableEditableFormFields} title={item.original_sku ? `Original: ${item.original_sku}` : ''} className="sku-input" /></div>
                        <div><label className="mobile-label" htmlFor={`desc-${index}`}>Desc:</label><textarea id={`desc-${index}`} value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableEditableFormFields} className="description-textarea" /></div>
                        <div className="qty-cost-row">
                            <div><label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label><input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableEditableFormFields} className="qty-input" /></div>
                            <div><label className="mobile-label" htmlFor={`cost-${index}`}>Cost:</label><input id={`cost-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableEditableFormFields} className="price-input" /></div>
                        </div>
                    </div>
                ))}
              </div>
            </section>
            <section className="shipment-info card">
              <h3>Shipment Information</h3>
              <div className="form-grid">
                <label htmlFor="shipmentMethod">Method:</label>
                <select id="shipmentMethod" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableEditableFormFields} required={purchaseItems.length > 0}> {/* Required only if items exist */}
                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
                <label htmlFor="shipmentWeight">Weight (lbs):</label>
                <input type="number" id="shipmentWeight" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required={purchaseItems.length > 0} disabled={disableEditableFormFields} /> {/* Required only if items exist */}
              </div>
            </section>
             <div className="order-actions">
                <button type="submit" disabled={disableAllActions || processing} className="btn btn-gradient btn-shadow-lift btn-success process-order-button-specifics">
                    {processing ? 'Processing Single PO...' : 'PROCESS SINGLE SUPPLIER PO'}
                </button>
            </div>
        </form>
      )}

      {canDisplayProcessingForm && isMultiSupplierMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form multi-supplier-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="multi-supplier-assignment card">
                <h3>Assign Original Items to Suppliers</h3>
                {originalLineItems.length === 0 && <p>No original line items to assign.</p>}
                {originalLineItems.map((item) => (
                    <div key={`assign-item-${item.line_item_id}`} className="item-assignment-row">
                        <span>({item.quantity}) {item.original_sku || 'N/A'}</span>
                        <select value={lineItemAssignments[item.line_item_id] || ''} onChange={(e) => handleLineItemSupplierAssignment(item.line_item_id, e.target.value)} disabled={disableAllActions || suppliers.length === 0}>
                            <option value="">-- Assign Supplier --</option>
                            {(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name}</option>))}
                        </select>
                    </div>
                ))}
            </section>

            {[...new Set(Object.values(lineItemAssignments))].filter(id => id).map(supplierId => { // Iterate over unique assigned supplier IDs
                const supplier = suppliers.find(s => s.id === parseInt(supplierId, 10));
                if (!supplier) return null; // Should not happen if IDs are from selection
                const itemsForThisSupplier = originalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supplierId);
                return (
                    <section key={supplierId} className="supplier-po-draft card">
                        <h4>PO Draft for: {supplier.name}</h4>
                        <div className="purchase-items-grid multi-supplier-items">
                            {itemsForThisSupplier.map(item => (
                                <div key={`multi-item-${item.line_item_id}`} className="item-row-multi">
                                    <div className="item-info-multi">
                                        Qty {item.quantity} of {item.original_sku || 'N/A'}
                                    </div>
                                    <div className="item-description-multi">
                                        <label className="mobile-label" htmlFor={`desc-multi-${item.line_item_id}`}>Description:</label>
                                        <textarea
                                            id={`desc-multi-${item.line_item_id}`}
                                            value={multiSupplierItemDescriptions[item.line_item_id] || ''}
                                            onChange={(e) => handleMultiSupplierItemDescriptionChange(item.line_item_id, e.target.value)}
                                            placeholder="Item Description for PO"
                                            rows={2} // Keep rows consistent
                                            disabled={disableAllActions}
                                            className="description-textarea-multi" // Ensure styling is applied
                                        />
                                    </div>
                                    <div className="item-cost-multi">
                                      <label htmlFor={`cost-multi-${item.line_item_id}`} className="mobile-label">Unit Cost:</label>
                                      <input
                                          id={`cost-multi-${item.line_item_id}`} // Unique ID
                                          type="number"
                                          value={multiSupplierItemCosts[item.line_item_id] || ''}
                                          onChange={(e) => handleMultiSupplierItemCostChange(item.line_item_id, e.target.value)}
                                          step="0.01"
                                          min="0"
                                          placeholder="0.00"
                                          required // Cost is required per item
                                          disabled={disableAllActions}
                                          className="price-input"
                                      />
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="form-grid shipment-details-multi card-inset">
                            <h5>Shipment Details for this PO (Optional - for Label Generation)</h5>
                            <div className="form-group">
                                <label htmlFor={`shipMethod-multi-${supplierId}`}>Method:</label>
                                <select
                                    id={`shipMethod-multi-${supplierId}`}
                                    value={multiSupplierShipmentDetails[supplierId]?.method || ''} // Default to empty if not set, allowing "-- No Label"
                                    onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'method', e.target.value)}
                                    disabled={disableAllActions}
                                >
                                    <option value="">-- No Label / Method --</option>
                                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                </select>
                            </div>
                            <div className="form-group">
                                <label htmlFor={`shipWeight-multi-${supplierId}`}>Weight (lbs):</label>
                                <input
                                    id={`shipWeight-multi-${supplierId}`}
                                    type="number"
                                    value={multiSupplierShipmentDetails[supplierId]?.weight || ''}
                                    onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'weight', e.target.value)}
                                    step="0.1"
                                    min="0.1"
                                    placeholder="e.g., 5.0"
                                    disabled={disableAllActions || !multiSupplierShipmentDetails[supplierId]?.method} // Disable if no method selected
                                    className="price-input" 
                                />
                            </div>
                        </div>
                        <div className="form-grid">
                            <label htmlFor={`poNotes-${supplierId}`}>PO Notes for {supplier.name}:</label>
                            <textarea id={`poNotes-${supplierId}`} value={poNotesBySupplier[supplierId] || ''} onChange={(e) => handlePoNotesBySupplierChange(supplierId, e.target.value)} rows="3" disabled={disableAllActions} />
                        </div>
                    </section>
                );
            })}
            <div className="order-actions">
                 <button type="submit" disabled={disableAllActions || processing || [...new Set(Object.values(lineItemAssignments))].filter(id => id).length === 0} className="btn btn-gradient btn-shadow-lift btn-success process-order-button-specifics">
                    {processing ? 'Processing Multiple POs...' : 'PROCESS ALL ASSIGNED POs'}
                </button>
            </div>
        </form>
      )}

      <div className="manual-actions-section" style={{marginTop: "20px"}}>
           {/* Only show "Mark as Completed Offline" if order status is international_manual or pending AND not already processed/completed */}
           {order && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') && !isActuallyProcessed && !isActuallyCompletedOffline && (
              <button onClick={() => handleManualStatusUpdate('Completed Offline')} className="btn btn-gradient btn-shadow-lift btn-success manual-action-button-specifics" disabled={disableAllActions}>
                  {manualStatusUpdateInProgress && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
           {/* Only show "Process Manually (Set to Pending)" if order status is 'new' AND not already processed/completed */}
           {order && order.status?.toLowerCase() === 'new' && !isActuallyProcessed && !isActuallyCompletedOffline && (
              <div style={{ marginTop: '10px', textAlign: 'center' }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); if (!disableAllActions) handleManualStatusUpdate('pending');}}
                      className={`link-button ${(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'link-button-updating' : ''}`}
                      style={{ fontSize: '0.9em', color: !(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'var(--text-secondary)' : undefined }}
                      aria-disabled={disableAllActions || (manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new')}> {/* More specific disabled state */}
                      {(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                  </a>
              </div>
          )}
      </div>

      <div className="order-actions" style={{ marginTop: '20px', textAlign: 'center' }}>
          {/* Show "BACK TO DASHBOARD" if new success message OR if already processed/completed */}
          {(isActuallyProcessed || isActuallyCompletedOffline || processSuccess) && (
              <button type="button" onClick={() => navigate('/')} className="btn btn-gradient btn-shadow-lift btn-primary back-to-dashboard-button-specifics" disabled={disableAllActions && !processSuccess}> {/* Disable only if general actions are disabled AND no new success */}
                  BACK TO DASHBOARD
              </button>
          )}
          {/* Show "already processed" message ONLY if it's actually processed/completed AND no NEW success message is being shown */}
          {(isActuallyProcessed || isActuallyCompletedOffline) && !processSuccess && (
              <div style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
                  This order has been {order.status?.toLowerCase()} and no further automated actions are available.
              </div>
          )}
      </div>
    </div>
  );
}

export default OrderDetail;