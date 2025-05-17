// OrderDetail.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import './OrderDetail.css';
import { useAuth } from '../contexts/AuthContext';

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
  if (lowerMethodString.includes('free shipping')) return 'UPS Ground';
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
  useEffect(() => { setPurchaseItemsRef.current = setPurchaseItems; }, [setPurchaseItems]); // Added dependency
  const purchaseItemsRef = useRef(purchaseItems);
  useEffect(() => { purchaseItemsRef.current = purchaseItems; }, [purchaseItems]);

  const cleanPullSuffix = " - clean pull";

  const originalLineItems = orderData?.line_items || [];

  useEffect(() => {
    const currentLineItemsCount = originalLineItems.length;
    
    if (isMultiSupplierMode && currentLineItemsCount <= 1) {
      setIsMultiSupplierMode(false); 
      if (selectedMainSupplierTrigger === MULTI_SUPPLIER_MODE_VALUE) {
        setSelectedMainSupplierTrigger(''); 
      }
    }
  }, [originalLineItems.length, isMultiSupplierMode, selectedMainSupplierTrigger, setIsMultiSupplierMode, setSelectedMainSupplierTrigger, MULTI_SUPPLIER_MODE_VALUE]);

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
            // setMultiSupplierItemDescriptions({}); // This was potentially cleared too early, re-init below
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
                setMultiSupplierItemDescriptions(initialMultiDesc); // Initialize here
            } else {
                setPurchaseItemsRef.current([]);
                setMultiSupplierItemDescriptions({}); // Clear if no line items
            }
        } else if (fetchedOrderData?.order) { 
            setOriginalCustomerShippingMethod(formatShippingMethod(fetchedOrderData.order.customer_shipping_method) || 'UPS Ground');
        }

    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message || "An unknown error occurred.");
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, cleanPullSuffix, VITE_API_BASE_URL, currentUser, setPurchaseItemsRef]); // Added setPurchaseItemsRef

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
    // Check orderData and line_items before proceeding
    if (!currentUser || !orderData?.line_items || orderData.line_items.length === 0) return;
    
    const fetchAllSpares = async () => {
        setLoadingSpares(true);
        const sparesMap = {};
        const token = await currentUser.getIdToken(true);
        for (const item of orderData.line_items) { // Use orderData.line_items directly
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
  }, [orderData?.line_items, currentUser, VITE_API_BASE_URL]); // Dependency on orderData.line_items

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
            // Use the callback version of setState for purchaseItems to ensure we have the latest state
            setPurchaseItemsRef.current(prevItems => {
                const updatedItems = [...prevItems];
                if (updatedItems[skuToLookup.index]?.skuInputValue === debouncedSku) { 
                    let newDescription = data.description;
                    if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) {
                        newDescription += cleanPullSuffix;
                    } else if (!newDescription) { 
                        const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                        newDescription = (existingDesc ? existingDesc + " " : "") + cleanPullSuffix.trim();
                        if (newDescription.startsWith(" " + cleanPullSuffix.trim())) newDescription = cleanPullSuffix.trim(); 
                    }
                    updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
                }
                return updatedItems;
            });
        } else if (response.status === 401 || response.status === 403) {
            console.error("Unauthorized to fetch SKU description.");
        }
      } catch (error) { if (error.name !== 'AbortError') console.error("Error fetching description:", error); }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, VITE_API_BASE_URL, currentUser, isMultiSupplierMode, setPurchaseItemsRef]); 
  
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
        setShipmentMethod(originalCustomerShippingMethod); 
        setShipmentWeight('');
        setLineItemAssignments({}); // Clear previous assignments
        setPoNotesBySupplier({});   // Clear previous notes
        setMultiSupplierItemCosts({}); // Clear previous costs
        
        // Re-initialize descriptions for multi-supplier mode based on current original line items
        const initialMultiDesc = {};
        if (originalLineItems) { // originalLineItems is already defined in component scope
            originalLineItems.forEach(item => {
                let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) {
                    defaultDescription += cleanPullSuffix;
                } else if (!defaultDescription && item.original_sku) {
                     defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
                }
                initialMultiDesc[item.line_item_id] = defaultDescription;
            });
        }
        setMultiSupplierItemDescriptions(initialMultiDesc);
        setMultiSupplierShipmentDetails({}); // Clear previous shipment details
    } else { 
        setIsMultiSupplierMode(false);
        const s = suppliers.find(sup => sup.id === parseInt(value, 10));
        setSingleOrderPoNotes(s?.defaultponotes || '');
        setShipmentMethod(originalCustomerShippingMethod); 
        // Clear multi-supplier specific states as they are not relevant for single supplier mode
        setLineItemAssignments({});
        setPoNotesBySupplier({});
        setMultiSupplierItemCosts({});
        setMultiSupplierItemDescriptions({}); // Clear these as they are specific to multi-supplier items
        setMultiSupplierShipmentDetails({});
    }
  };
  const handleSingleOrderPoNotesChange = (e) => setSingleOrderPoNotes(e.target.value);
  const handleLineItemSupplierAssignment = (originalLineItemId, supplierId) => {
    setLineItemAssignments(prev => ({ ...prev, [originalLineItemId]: supplierId }));
    if (supplierId && !poNotesBySupplier[supplierId]) {
        const s = suppliers.find(sup => sup.id === parseInt(supplierId, 10));
        setPoNotesBySupplier(prev => ({ ...prev, [supplierId]: s?.defaultponotes || '' }));
    }
    if (supplierId && isMultiSupplierMode && !multiSupplierShipmentDetails[supplierId]) {
        setMultiSupplierShipmentDetails(prev => ({
            ...prev,
            [supplierId]: { method: originalCustomerShippingMethod, weight: '' } 
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
            ...(prev[supplierId] || { method: originalCustomerShippingMethod, weight: '' }), 
            [field]: value
        }
    }));
  };
  const handlePurchaseItemChange = (index, field, value) => {
    // Use callback form of setState for purchaseItems to ensure access to the latest state
    setPurchaseItemsRef.current(prevItems => {
        const items = [...prevItems];
        items[index] = { ...items[index], [field]: value };
        if (field === 'sku') {
            const trimmedSku = String(value).trim();
            items[index].sku = trimmedSku; 
            items[index].skuInputValue = trimmedSku; 
            setSkuToLookup({ index, sku: trimmedSku });
        }
        return items;
    });
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

  const handlePartNumberLinkClick = async (e, partNumber) => {
    e.preventDefault(); 

    if (orderData?.order?.bigcommerce_order_id) { // Check if orderData and order exist
        await handleCopyToClipboard(orderData.order.bigcommerce_order_id);
    }

    if (!currentUser) {
        setStatusUpdateMessage("Please log in to perform this action.");
        return; 
    }
    
    const currentOrderStatus = orderData?.order?.status?.toLowerCase();
    const trimmedPartNumberForStatusCheck = String(partNumber || '').trim();

    if (currentOrderStatus === 'new' && trimmedPartNumberForStatusCheck) {
      try {
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
                navigate('/login'); 
            }
            throw new Error(err);
        }
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, false); 
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${trimmedPartNumberForStatusCheck}`);
      } catch (err) {
        setStatusUpdateMessage(`Error updating status for part ${trimmedPartNumberForStatusCheck}: ${err.message}`);
      }
    } else if (trimmedPartNumberForStatusCheck && currentOrderStatus && !['new', 'rfq sent', 'processed', 'completed offline', 'pending'].includes(currentOrderStatus)) {
      // Commented out to avoid overriding more important messages like "Order processed successfully"
      // setStatusUpdateMessage(`Order status is '${orderData?.order?.status}'. Part status not updated.`);
    }

    const brokerbinUrl = createBrokerbinLink(partNumber);
    window.open(brokerbinUrl, '_blank', 'noopener,noreferrer');
  };

  const handleManualStatusUpdate = async (newStatus) => {
    if (!currentUser) { setStatusUpdateMessage("Please log in to update status."); return; }
    if (!orderId || !VITE_API_BASE_URL) { setStatusUpdateMessage("Configuration error."); return; } 
    setManualStatusUpdateInProgress(true); setStatusUpdateMessage(''); 
    try {
        const token = await currentUser.getIdToken(true);
        const statusApiUrl = `${VITE_API_BASE_URL}/orders/${orderId}/status`;
        const response = await fetch(statusApiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` }, body: JSON.stringify({ status: newStatus }) });
        const responseData = await response.json().catch(() => null); 
        if (!response.ok) { let err = responseData?.details || responseData?.error || `HTTP error ${response.status}`; if(response.status===401||response.status===403) {err="Unauthorized. Please log in again."; navigate('/login');} throw new Error(err); }
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal, false); 
    } catch (err) { setStatusUpdateMessage(`Error updating status: ${err.message}`);
    } finally { setManualStatusUpdateInProgress(false); }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    if (!currentUser) { setProcessError("Please log in."); return; }
    setProcessing(true); setProcessError(null); setProcessSuccess(false); setProcessSuccessMessage(''); setProcessedPOsInfo([]); setStatusUpdateMessage('');

    let payloadAssignments = [];
    
    if (isMultiSupplierMode) {
        const assignedSupplierIds = [...new Set(Object.values(lineItemAssignments))].filter(id => id); 
        
        if (originalLineItems.length > 0) {
            if (assignedSupplierIds.length === 0) {
                setProcessError("Multi-Supplier Mode: Assign items to at least one supplier.");
                setProcessing(false); return;
            }
            const allOriginalItemsAssigned = originalLineItems.every(item => !!lineItemAssignments[item.line_item_id]);
            if (!allOriginalItemsAssigned) {
                setProcessError("Multi-Supplier Mode: Assign all original items to a supplier.");
                setProcessing(false); return;
            }
        }

        for (const supId of assignedSupplierIds) {
            const itemsForThisSupplier = originalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supId);
            if (itemsForThisSupplier.length > 0) {
                let itemCostValidationError = null;
                const poLineItems = itemsForThisSupplier.map(item => {
                    const costStr = multiSupplierItemCosts[item.line_item_id];
                    const costFloat = parseFloat(costStr);
                    if (costStr === undefined || costStr === '' || isNaN(costFloat) || costFloat < 0) {
                        itemCostValidationError = `Missing or invalid unit cost for SKU ${item.original_sku || 'N/A'} (Supplier: ${suppliers.find(s=>s.id===parseInt(supId,10))?.name}).`;
                        return null; 
                    }
                    let descriptionForPo = multiSupplierItemDescriptions[item.line_item_id];
                    if (descriptionForPo === undefined) { 
                        descriptionForPo = item.hpe_po_description || item.line_item_name || `${item.original_sku || ''}${cleanPullSuffix}`;
                    }
                    if (!String(descriptionForPo).trim()) {
                        itemCostValidationError = `Missing description for SKU ${item.original_sku || 'N/A'} (Supplier: ${suppliers.find(s=>s.id===parseInt(supId,10))?.name}).`;
                        return null;
                    }
                    return {
                        original_order_line_item_id: item.line_item_id,
                        sku: item.hpe_option_pn || item.original_sku, 
                        description: String(descriptionForPo).trim(),
                        quantity: item.quantity,
                        unit_cost: costFloat.toFixed(2),
                        condition: 'New', 
                    };
                }).filter(Boolean); 

                if (itemCostValidationError) { setProcessError(itemCostValidationError); setProcessing(false); return; }
                if (poLineItems.length !== itemsForThisSupplier.length && itemsForThisSupplier.length > 0) {
                    setProcessError("One or more items for a supplier had validation errors (e.g., missing cost/description)."); 
                    setProcessing(false); return; 
                }
                
                const shipmentDetailsForThisPo = multiSupplierShipmentDetails[supId] || {};
                const currentPoWeight = shipmentDetailsForThisPo.weight;
                const currentPoMethod = shipmentDetailsForThisPo.method;

                if (currentPoMethod && (!currentPoWeight || parseFloat(currentPoWeight) <= 0)) {
                    setProcessError(`Invalid/missing weight for PO to ${suppliers.find(s=>s.id === parseInt(supId, 10))?.name} when a shipping method is selected.`);
                    setProcessing(false); return;
                }
                if (!currentPoMethod && currentPoWeight && parseFloat(currentPoWeight) > 0) {
                    setProcessError(`Shipping method required for PO to ${suppliers.find(s=>s.id === parseInt(supId, 10))?.name} when weight is provided.`);
                    setProcessing(false); return;
                }
                
                payloadAssignments.push({
                    supplier_id: parseInt(supId, 10),
                    payment_instructions: poNotesBySupplier[supId] || "",
                    po_line_items: poLineItems,
                    total_shipment_weight_lbs: currentPoWeight ? parseFloat(currentPoWeight).toFixed(1) : null,
                    shipment_method: currentPoMethod || null 
                });
            }
        }
        if (payloadAssignments.length === 0 && originalLineItems.length > 0) {
             setProcessError("No items were successfully assigned or configured for PO generation.");
             setProcessing(false); return;
        }
    } else { 
        const singleSelectedSupId = selectedMainSupplierTrigger;
        if (!singleSelectedSupId || singleSelectedSupId === MULTI_SUPPLIER_MODE_VALUE) {
            setProcessError("Please select a supplier."); setProcessing(false); return;
        }
        // Use purchaseItemsRef.current for validation in single supplier mode as it reflects user edits
        const currentPurchaseItems = purchaseItemsRef.current; 
        if (currentPurchaseItems.length > 0) { // Validate shipping only if there are items in the PO form
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight."); setProcessing(false); return; }
            if (!shipmentMethod) { setProcessError("Please select a shipment method."); setProcessing(false); return; }
        }

        let itemValidationError = null;
        const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10); const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1}: Quantity must be > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1}: Unit cost is invalid.`; return null; }
            if (!String(item.sku).trim()) { itemValidationError = `Item #${index + 1}: SKU is required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `Item #${index + 1}: Description is required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.sku).trim(), description: String(item.description).trim(), quantity: quantityInt, unit_cost: costFloat.toFixed(2), condition: item.condition || 'New' };
        }).filter(Boolean);

        if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
        // This condition means if there were original items, the PO form must also result in items.
        // If there were no original items, it's okay for finalPurchaseItems to be empty (e.g. manual PO without items, if backend supports)
        if (finalPurchaseItems.length === 0 && originalLineItems.length > 0) { 
            setProcessError("No valid line items for PO. Please check quantities, costs, SKUs, and descriptions."); 
            setProcessing(false); return; 
        }
        
        // Only create an assignment if there are items in the PO form OR if there were no original items (manual PO scenario)
        if (finalPurchaseItems.length > 0 || originalLineItems.length === 0) {
             payloadAssignments.push({
                supplier_id: parseInt(singleSelectedSupId, 10),
                payment_instructions: singleOrderPoNotes,
                // Send shipping details only if there are items in the final PO
                total_shipment_weight_lbs: finalPurchaseItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null, 
                shipment_method: finalPurchaseItems.length > 0 ? shipmentMethod : null, 
                po_line_items: finalPurchaseItems
            });
        }
    }
    
    if (payloadAssignments.length === 0 && originalLineItems.length > 0 ) {
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
        await fetchOrderAndSuppliers(ac.signal, true); 
    } catch (err) {
        setProcessError(err.message || "An unexpected error occurred during processing.");
        setProcessSuccess(false); 
        setProcessedPOsInfo([]); 
    } finally {
        setProcessing(false);
    }
  };

  if (authLoading) return <div className="loading-message">Loading session...</div>;
  if (!currentUser) return <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}><h2>Order Details</h2><p className="error-message">Please <Link to="/login">log in</Link>.</p></div>;
  if (loading && !orderData && !processSuccess) return <div className="loading-message">Loading order details...</div>; 
  if (error) return <div className="error-message">Error: {error}</div>;
  
  const order = orderData?.order; 

  if (!order && !processSuccess) { 
      return <p style={{ textAlign: 'center', marginTop: '20px' }}>Order details not found or error loading.</p>;
  }

  const isActuallyProcessed = order?.status?.toLowerCase() === 'processed';
  const isActuallyCompletedOffline = order?.status?.toLowerCase() === 'completed offline';
  const canDisplayProcessingForm = !processSuccess && !(isActuallyProcessed || isActuallyCompletedOffline);
  const disableAllActions = processing || manualStatusUpdateInProgress;
  const disableEditableFormFields = isActuallyProcessed || isActuallyCompletedOffline || disableAllActions || processSuccess;

  let displayOrderDate = 'N/A';
  if (order?.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) { /* ignore */ }
  const displayCustomerShippingMethod = formatShippingMethod(order?.customer_shipping_method);

  return (
    <div className="order-detail-container">
      <div className="order-title-section">
        <h2>
          <span>Order #{order?.bigcommerce_order_id || orderId} </span>
          <button title="Copy Order ID" onClick={() => handleCopyToClipboard(order?.bigcommerce_order_id)} className="copy-button" disabled={!order?.bigcommerce_order_id}>📋</button>
          {clipboardStatus && <span className="clipboard-status">{clipboardStatus}</span>}
        </h2>
        {order && ( 
            <span className={`order-status-badge status-${(order.status || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
            {order.status || 'Unknown'}
            </span>
        )}
      </div>

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
                                {poInfo.po_pdf_gcs_uri && ( <a href={poInfo.po_pdf_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link"> View PO </a> )}
                                {poInfo.packing_slip_gcs_uri && ( <a href={poInfo.packing_slip_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link"> View Packing Slip </a> )}
                                {poInfo.label_gcs_uri && ( <a href={poInfo.label_gcs_uri} target="_blank" rel="noopener noreferrer" className="pdf-link"> View Label </a> )}
                            </div>
                        ) : ( <p className="no-documents-note">No PDF document links available for this PO.</p> )}
                    </div>
                );
              })}
            </div>
          )}
        </div>
      )}

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
                <a href={createBrokerbinLink(item.original_sku)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.original_sku}`} onClick={(e) => handlePartNumberLinkClick(e, item.original_sku)}>{String(item.original_sku || 'N/A').trim()}</a>
                {loadingSpares && item.hpe_pn_type === 'option' && !lineItemSpares[item.line_item_id] && <span className="loading-text"> (loading spare...)</span>}
                {lineItemSpares[item.line_item_id] && ( <span style={{ fontStyle: 'italic', marginLeft: '5px' }}>( <a href={createBrokerbinLink(lineItemSpares[item.line_item_id])} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${lineItemSpares[item.line_item_id]}`} onClick={(e) => handlePartNumberLinkClick(e, lineItemSpares[item.line_item_id])}>{lineItemSpares[item.line_item_id]}</a> )</span> )}
                {item.hpe_option_pn && String(item.hpe_option_pn).trim() !== String(item.original_sku).trim() && String(item.hpe_option_pn).trim() !== lineItemSpares[item.line_item_id] && ( <span>{' ('} <a href={createBrokerbinLink(item.hpe_option_pn)} target="_blank" rel="noopener noreferrer" className="link-button" title={`Copy Order ID & Brokerbin: ${item.hpe_option_pn}`} onClick={(e) => handlePartNumberLinkClick(e, item.hpe_option_pn)}>{String(item.hpe_option_pn).trim()}</a> {')'}</span> )}
                <span> @ ${parseFloat(item.sale_price || 0).toFixed(2)}</span>
            </p>
        ))}
      </section>
      )}

     {canDisplayProcessingForm && (
        <section className="supplier-mode-selection card">
        <h3>Begin Order Fulfillment</h3>
        <div className="form-grid">
            <label htmlFor="mainSupplierTrigger" style={{ marginRight: '8px' }}>Supplier Mode:</label> 
            <select 
                id="mainSupplierTrigger" 
                value={selectedMainSupplierTrigger} 
                onChange={handleMainSupplierTriggerChange} 
                disabled={disableAllActions || suppliers.length === 0}
                style={{ flexGrow: 1 }}
            >
                <option value="">-- Select Supplier --</option>
                {originalLineItems.length > 1 && ( 
                    <option value={MULTI_SUPPLIER_MODE_VALUE}>** Use Multiple Suppliers **</option>
                )}
                {(suppliers || []).map(supplier => (
                    <option key={supplier.id} value={supplier.id}>
                        {supplier.name || 'Unnamed Supplier'}
                    </option>
                ))}
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
                {purchaseItemsRef.current.map((item, index) => ( // Use purchaseItemsRef.current for rendering
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
                <select id="shipmentMethod" value={shipmentMethod} onChange={handleShipmentMethodChange} disabled={disableEditableFormFields} required={purchaseItemsRef.current.length > 0}> 
                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
                <label htmlFor="shipmentWeight">Weight (lbs):</label>
                <input type="number" id="shipmentWeight" value={shipmentWeight} onChange={handleShipmentWeightChange} step="0.1" min="0.1" placeholder="e.g., 5.0" required={purchaseItemsRef.current.length > 0} disabled={disableEditableFormFields} /> 
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

            {[...new Set(Object.values(lineItemAssignments))].filter(id => id).map(supplierId => { 
                const supplier = suppliers.find(s => s.id === parseInt(supplierId, 10));
                if (!supplier) return null; 
                const itemsForThisSupplier = originalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supplierId);
                return (
                    <section key={supplierId} className="supplier-po-draft card">
                        <h4>PO Draft for: {supplier.name}</h4>
                        <div className="purchase-items-grid multi-supplier-items">
                            {itemsForThisSupplier.map(item => (
                                <div key={`multi-item-${item.line_item_id}`} className="item-row-multi">
                                    <div className="item-info-multi"> Qty {item.quantity} of {item.original_sku || 'N/A'} </div>
                                    <div className="item-description-multi">
                                        <label className="mobile-label" htmlFor={`desc-multi-${item.line_item_id}`}>Description:</label>
                                        <textarea id={`desc-multi-${item.line_item_id}`} value={multiSupplierItemDescriptions[item.line_item_id] || ''} onChange={(e) => handleMultiSupplierItemDescriptionChange(item.line_item_id, e.target.value)} placeholder="Item Description for PO" rows={2} disabled={disableAllActions} className="description-textarea-multi" />
                                    </div>
                                    <div className="item-cost-multi">
                                      <label htmlFor={`cost-multi-${item.line_item_id}`} className="mobile-label">Unit Cost:</label>
                                      <input id={`cost-multi-${item.line_item_id}`} type="number" value={multiSupplierItemCosts[item.line_item_id] || ''} onChange={(e) => handleMultiSupplierItemCostChange(item.line_item_id, e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableAllActions} className="price-input" />
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="form-grid shipment-details-multi card-inset">
                            <h5>Shipment Details for this PO (Optional - for Label Generation)</h5>
                            <div className="form-group">
                                <label htmlFor={`shipMethod-multi-${supplierId}`}>Method:</label>
                                <select id={`shipMethod-multi-${supplierId}`} value={multiSupplierShipmentDetails[supplierId]?.method || ''} onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'method', e.target.value)} disabled={disableAllActions} >
                                    <option value="">-- No Label / Method --</option>
                                    {SHIPPING_METHODS_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                                </select>
                            </div>
                            <div className="form-group">
                                <label htmlFor={`shipWeight-multi-${supplierId}`}>Weight (lbs):</label>
                                <input id={`shipWeight-multi-${supplierId}`} type="number" value={multiSupplierShipmentDetails[supplierId]?.weight || ''} onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'weight', e.target.value)} step="0.1" min="0.1" placeholder="e.g., 5.0" disabled={disableAllActions || !multiSupplierShipmentDetails[supplierId]?.method} className="price-input" />
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
           {order && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') && !isActuallyProcessed && !isActuallyCompletedOffline && (
              <button onClick={() => handleManualStatusUpdate('Completed Offline')} className="btn btn-gradient btn-shadow-lift btn-success manual-action-button-specifics" disabled={disableAllActions}>
                  {manualStatusUpdateInProgress && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
           {order && order.status?.toLowerCase() === 'new' && !isActuallyProcessed && !isActuallyCompletedOffline && (
              <div style={{ marginTop: '10px', textAlign: 'center' }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); if (!disableAllActions) handleManualStatusUpdate('pending');}}
                      className={`link-button ${(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'link-button-updating' : ''}`}
                      style={{ fontSize: '0.9em', color: !(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'var(--text-secondary)' : undefined }}
                      aria-disabled={disableAllActions || (manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new')}> 
                      {(manualStatusUpdateInProgress && order.status?.toLowerCase() === 'new') ? 'Updating...' : 'Or, Process Manually (Set to Pending)'}
                  </a>
              </div>
          )}
      </div>

      <div className="order-actions" style={{ marginTop: '20px', textAlign: 'center' }}>
          {(isActuallyProcessed || isActuallyCompletedOffline || processSuccess) && (
              <button type="button" onClick={() => navigate('/')} className="btn btn-gradient btn-shadow-lift btn-primary back-to-dashboard-button-specifics" disabled={disableAllActions && !processSuccess}> 
                  BACK TO DASHBOARD
              </button>
          )}
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