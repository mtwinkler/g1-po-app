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
  const lowerMethod = methodString.toLowerCase().trim();

  if (lowerMethod.includes('fedex')) {
    if (lowerMethod.includes('ground')) return 'FEDEX_GROUND';
    if (lowerMethod.includes('2day') || lowerMethod.includes('2 day')) return 'FEDEX_2_DAY';
    if (lowerMethod.includes('priority overnight')) return 'FEDEX_PRIORITY_OVERNIGHT';
    if (lowerMethod.includes('standard overnight')) return 'FEDEX_STANDARD_OVERNIGHT';
  }

  if (lowerMethod.includes('next day air early a.m.') || lowerMethod.includes('next day air early am') || lowerMethod.includes('next day air e')) return 'UPS Next Day Air Early A.M.';
  if (lowerMethod.includes('next day air') || lowerMethod.includes('nda')) return 'UPS Next Day Air';
  if (lowerMethod.includes('2nd day air') || lowerMethod.includes('second day air')) return 'UPS 2nd Day Air';
  if (lowerMethod.includes('ground')) return 'UPS Ground';
  if (lowerMethod.includes('worldwide expedited')) return 'UPS Worldwide Expedited';
  if (lowerMethod.includes('worldwide express')) return 'UPS Worldwide Express';
  if (lowerMethod.includes('worldwide saver')) return 'UPS Worldwide Saver';
  if (lowerMethod.includes('free shipping')) return 'UPS Ground';

  if (lowerMethod === 'ups ground') return 'UPS Ground';
  if (lowerMethod === 'ups 2nd day air') return 'UPS 2nd Day Air';
  if (lowerMethod === 'ups next day air') return 'UPS Next Day Air';
  if (lowerMethod === 'ups next day air early a.m.') return 'UPS Next Day Air Early A.M.';
  if (lowerMethod === 'ups worldwide expedited') return 'UPS Worldwide Expedited';
  if (lowerMethod === 'ups worldwide express') return 'UPS Worldwide Express';
  if (lowerMethod === 'ups worldwide saver') return 'UPS Worldwide Saver';

  const bcMatch = methodString.match(/\(([^)]+)\)/);
  if (bcMatch && bcMatch[1]) {
    const extracted = bcMatch[1].trim();
    const innerFormatted = formatShippingMethod(extracted);
    return innerFormatted !== 'N/A' ? innerFormatted : extracted;
  }

  return String(methodString).trim();
};


const MULTI_SUPPLIER_MODE_VALUE = "_MULTI_SUPPLIER_MODE_";
const G1_ONSITE_FULFILLMENT_VALUE = "_G1_ONSITE_FULFILLMENT_";

const SHIPPING_METHODS_OPTIONS = [
    { value: "UPS Ground", label: "UPS Ground", carrier: "ups" },
    { value: "UPS 2nd Day Air", label: "UPS 2nd Day Air", carrier: "ups" },
    { value: "UPS Next Day Air", label: "UPS Next Day Air", carrier: "ups" },
    { value: "UPS Next Day Air Early A.M.", label: "UPS Next Day Air Early A.M.", carrier: "ups" },
    { value: "UPS Worldwide Expedited", label: "UPS Worldwide Expedited", carrier: "ups" },
    { value: "UPS Worldwide Express", label: "UPS Worldwide Express", carrier: "ups" },
    { value: "UPS Worldwide Saver", label: "UPS Worldwide Saver", carrier: "ups" },
    { value: "FEDEX_GROUND", label: "FedEx Ground", carrier: "fedex" },
    { value: "FEDEX_2_DAY", label: "FedEx 2Day", carrier: "fedex" },
    { value: "FEDEX_PRIORITY_OVERNIGHT", label: "FedEx Priority Overnight", carrier: "fedex" },
    { value: "FEDEX_STANDARD_OVERNIGHT", label: "FedEx Standard Overnight", carrier: "fedex" }
];

const getSelectedShippingOption = (methodValue) => {
  const foundOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === methodValue);
  return foundOption || { value: methodValue, label: methodValue || 'N/A', carrier: null };
};

// --- Profit Display Component with conditional background ---
const ProfitDisplay = ({ info }) => {
    if (!info || !info.isCalculable) {
        return null;
    }

    const formatCurrency = (value) => {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(value);
    };

    const isProfitable = info.profitAmount >= 0;
    
    const profitableBgColor = 'rgba(40, 167, 69, 0.6)'; 
    const lossBgColor = 'rgba(220, 53, 69, 0.6)';       

    const cardStyle = {
        backgroundColor: isProfitable ? profitableBgColor : lossBgColor,
    };

    const profitAmountColor = isProfitable ? 'var(--success-text)' : 'var(--error-text)';

    return (
        <div className="profit-display-card card" style={cardStyle}>
            <h3>Profitability Analysis</h3>
            <div className="profit-grid">
                <span>Revenue:</span>
                <span>{formatCurrency(info.totalRevenue)}</span>

                <span>Cost:</span>
                <span>{formatCurrency(info.totalCost)}</span>

                <hr style={{ gridColumn: '1 / -1', border: 'none', borderTop: '1px solid #ccc', margin: '12px 0' }} />

                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 'bold' }}>Profit:</div>
                    <div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>
                        {formatCurrency(info.profitAmount)}
                    </div>
                </div>

                <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 'bold' }}>Margin:</div>
                    <div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>
                        {info.profitMargin.toFixed(2)}%
                    </div>
                </div>
            </div>
        </div>
    );
};


function OrderDetail() {
  const { orderId } = useParams();
  const { currentUser, loading: authLoading, apiService } = useAuth();
  const navigate = useNavigate();

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
  const [seeQuotesStatus, setSeeQuotesStatus] = useState('');

  const [purchaseItems, setPurchaseItems] = useState([]);
  const [shipmentMethod, setShipmentMethod] = useState('UPS Ground');
  const [shipmentWeight, setShipmentWeight] = useState('');

  const [selectedMainSupplierTrigger, setSelectedMainSupplierTrigger] = useState('');
  const [isMultiSupplierMode, setIsMultiSupplierMode] = useState(false);
  const [isG1OnsiteFulfillmentMode, setIsG1OnsiteFulfillmentMode] = useState(false);
  const [singleOrderPoNotes, setSingleOrderPoNotes] = useState('');
  const [lineItemAssignments, setLineItemAssignments] = useState({});
  const [poNotesBySupplier, setPoNotesBySupplier] = useState({});
  const [multiSupplierItemCosts, setMultiSupplierItemCosts] = useState({});
  const [multiSupplierItemDescriptions, setMultiSupplierItemDescriptions] = useState({});
  const [multiSupplierShipmentDetails, setMultiSupplierShipmentDetails] = useState({});
  const [originalCustomerShippingMethod, setOriginalCustomerShippingMethod] = useState('UPS Ground');

  const [billToCustomerFedex, setBillToCustomerFedex] = useState(false);
  const [customerFedexAccountNumber, setCustomerFedexAccountNumber] = useState('');
  const [billToCustomerUps, setBillToCustomerUps] = useState(false);
  const [customerUpsAccountNumber, setCustomerUpsAccountNumber] = useState('');
  const [isBlindDropShip, setIsBlindDropShip] = useState(false);
  const [lineItemSpares, setLineItemSpares] = useState({});
  const [loadingSpares, setLoadingSpares] = useState(false);

  const [profitInfo, setProfitInfo] = useState({
      totalRevenue: 0,
      totalCost: 0,
      profitAmount: 0,
      profitMargin: 0,
      isCalculable: false
  });

  const cleanPullSuffix = " - clean pull";
  const originalLineItems = orderData?.line_items || []; 

  const currentSelectedShippingOption = getSelectedShippingOption(shipmentMethod);

  const handleBrandingChange = (event) => {
    setIsBlindDropShip(event.target.value === 'blind');
  };

  const handleSeeQuotesClick = async () => {
    if (!orderData?.order?.bigcommerce_order_id) {
      setSeeQuotesStatus('Error: Order number not available.');
      setTimeout(() => setSeeQuotesStatus(''), 3000);
      return;
    }
    const orderNumber = orderData.order.bigcommerce_order_id;
    const searchPhrase = `Show me, in list format, the quoted prices received only today for Brokerbin RFQ and order number ${orderNumber}. Also include any comments included with the quotes. Disregard anything below "From: Global One Technology" in the emails. Note that "ea" is an abbreviation for each.`;
    try {
      await navigator.clipboard.writeText(searchPhrase);
      setSeeQuotesStatus(`Gemini prompt copied!`);
      setTimeout(() => setSeeQuotesStatus(''), 3000);
    } catch (err) {
      console.error('Failed to copy search phrase to clipboard:', err);
      setSeeQuotesStatus('Error: Could not copy to clipboard. Please try manually.');
      setTimeout(() => setSeeQuotesStatus(''), 5000);
    }
  };

  useEffect(() => {
    if (isMultiSupplierMode && originalLineItems.length <= 1) {
      setIsMultiSupplierMode(false);
      if (selectedMainSupplierTrigger === MULTI_SUPPLIER_MODE_VALUE) {
        setSelectedMainSupplierTrigger('');
      }
    }
  }, [originalLineItems.length, isMultiSupplierMode, selectedMainSupplierTrigger]);

  const fetchOrderAndSuppliers = useCallback(async (signal, isPostProcessRefresh = false) => {
    if (!currentUser) {
        setLoading(false); setOrderData(null); setSuppliers([]); return;
    }
    setLoading(true); setError(null);

    if (!isPostProcessRefresh) {
        setProcessSuccess(false); setProcessSuccessMessage('');
        setProcessedPOsInfo([]); setProcessError(null);
        setIsBlindDropShip(false);
        setBillToCustomerFedex(false); 
        setCustomerFedexAccountNumber('');
        setBillToCustomerUps(false);
        setCustomerUpsAccountNumber('');
    }
    setStatusUpdateMessage('');

    try {
        const [fetchedOrderData, fetchedSuppliers] = await Promise.all([
            apiService.get(`/orders/${orderId}`),
            apiService.get(`/suppliers`)
        ]);
        if (signal?.aborted) return;

        setOrderData(fetchedOrderData); 
        setSuppliers(fetchedSuppliers || []);

        if (!isPostProcessRefresh) {
            setLineItemSpares({});
            setMultiSupplierItemCosts({});
            setMultiSupplierShipmentDetails({});
            setLineItemAssignments({});
            setPoNotesBySupplier({});
            
            if (fetchedOrderData?.order) {
                const orderDetails = fetchedOrderData.order;
                let determinedInitialShipMethod = 'UPS Ground';
                
                if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) {
                    const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
                    const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'ups');
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        setBillToCustomerUps(true);
                        setCustomerUpsAccountNumber(orderDetails.customer_ups_account_number || '');
                    }
                } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) {
                    const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
                     const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        setBillToCustomerFedex(true);
                        setCustomerFedexAccountNumber(orderDetails.customer_fedex_account_number || '');
                    }
                } else if (orderDetails.customer_shipping_method) { 
                    const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
                    const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
                    if (matchedOption) {
                        determinedInitialShipMethod = matchedOption.value;
                        if (matchedOption.carrier === 'ups' && orderDetails.is_bill_to_customer_account) {
                           setBillToCustomerUps(true);
                           setCustomerUpsAccountNumber(orderDetails.customer_ups_account_number || '');
                        } else if (matchedOption.carrier === 'fedex' && orderDetails.is_bill_to_customer_fedex_account) {
                           setBillToCustomerFedex(true);
                           setCustomerFedexAccountNumber(orderDetails.customer_fedex_account_number || '');
                        }
                    }
                }
                setShipmentMethod(determinedInitialShipMethod);
                setOriginalCustomerShippingMethod(determinedInitialShipMethod);
            }


            if (fetchedOrderData?.line_items) {
                const initialItemsForPoForm = fetchedOrderData.line_items.map(item => ({
                    original_order_line_item_id: item.line_item_id,
                    sku: item.hpe_option_pn || item.original_sku || '',
                    description: (item.hpe_po_description || item.line_item_name || '') + ( (item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
                    skuInputValue: item.hpe_option_pn || item.original_sku || '',
                    quantity: item.quantity || 1, unit_cost: '', condition: 'New',
                    original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn,
                    original_name: item.line_item_name, hpe_po_description: item.hpe_po_description,
                    hpe_pn_type: item.hpe_pn_type,
                }));
                setPurchaseItems(initialItemsForPoForm);

                const initialMultiDesc = {};
                fetchedOrderData.line_items.forEach(item => {
                    let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                    if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) defaultDescription += cleanPullSuffix;
                    else if (!defaultDescription && item.original_sku) defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
                    initialMultiDesc[item.line_item_id] = defaultDescription;
                });
                setMultiSupplierItemDescriptions(initialMultiDesc);
            } else {
                setPurchaseItems([]);
                setMultiSupplierItemDescriptions({});
            }
        } else if (fetchedOrderData?.order) {
            const orderDetails = fetchedOrderData.order;
            let determinedOriginalMethod = 'UPS Ground';
             if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) {
                const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === customerSelectedService && opt.carrier === 'ups')) determinedOriginalMethod = customerSelectedService;
            } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) {
                const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === customerSelectedService && opt.carrier === 'fedex')) determinedOriginalMethod = customerSelectedService;
            } else if (orderDetails.customer_shipping_method) {
                const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
                 if (SHIPPING_METHODS_OPTIONS.some(opt => opt.value === parsedOrderMethod)) determinedOriginalMethod = parsedOrderMethod;
            }
            setOriginalCustomerShippingMethod(determinedOriginalMethod);
        }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error("Error in fetchOrderAndSuppliers:", err);
        setError(err.data?.message || err.message || "An unknown error occurred fetching data.");
      }
    } finally {
        if (!signal || !signal.aborted) setLoading(false);
    }
  }, [orderId, cleanPullSuffix, currentUser, apiService]);

  useEffect(() => {
    if (authLoading) { setLoading(true); return; }
    const abortController = new AbortController();
    if (orderId && currentUser && apiService) {
        fetchOrderAndSuppliers(abortController.signal, false);
    }
    else if (!currentUser && !authLoading && orderId) { setLoading(false); setError("Please log in."); }
    else if (!orderId) { setError("Order ID missing."); setLoading(false); }
    return () => abortController.abort();
  }, [orderId, currentUser, authLoading, fetchOrderAndSuppliers, apiService]);

  // --- Profit Calculation useEffect ---
  useEffect(() => {
    if (!orderData || !orderData.order || !orderData.line_items) {
        if (profitInfo.isCalculable) { 
            setProfitInfo(prev => ({ ...prev, isCalculable: false }));
        }
        return;
    }

    let calculatedItemsRevenue = 0;
    if (originalLineItems && originalLineItems.length > 0) {
        calculatedItemsRevenue = originalLineItems.reduce((sum, item) => {
            const price = parseFloat(item.sale_price || 0);
            const quantity = parseInt(item.quantity || 0, 10);
            return sum + (price * quantity);
        }, 0);
    }
    const revenue = calculatedItemsRevenue;

    let cost = 0;
    let isCalculable = false;
    const orderStatus = orderData.order.status?.toLowerCase();

    if (orderStatus === 'processed') {
        if (orderData.order.hasOwnProperty('actual_cost_of_goods_sold')) {
            cost = parseFloat(orderData.order.actual_cost_of_goods_sold || 0);
        } else {
            cost = 0; 
            console.warn("Profit Calc (Processed Order): 'actual_cost_of_goods_sold' field not found in orderData.order. Cost will be shown as $0. Backend needs to provide this for accuracy.");
        }
        isCalculable = true; 
        if (!revenue && originalLineItems.length === 0) {
            isCalculable = false; 
        }
    } else if (isG1OnsiteFulfillmentMode) {
        cost = 0;
        isCalculable = revenue > 0 || originalLineItems.length === 0;
    } else if (isMultiSupplierMode) {
        const currentOriginalLineItems = orderData.line_items || [];
        const assignedItems = currentOriginalLineItems.filter(item => lineItemAssignments[item.line_item_id]);
        
        if (assignedItems.length > 0 && assignedItems.length === currentOriginalLineItems.length) {
            const allCostsEntered = assignedItems.every(item => {
                const itemCost = multiSupplierItemCosts[item.line_item_id];
                return itemCost !== undefined && itemCost !== '' && !isNaN(parseFloat(itemCost));
            });
            if (allCostsEntered) {
                cost = assignedItems.reduce((total, item) => {
                    const itemCostNum = parseFloat(multiSupplierItemCosts[item.line_item_id]);
                    const quantityNum = parseInt(item.quantity, 10);
                    return total + (itemCostNum * quantityNum);
                }, 0);
                isCalculable = true;
            }
        }
    } else if (selectedMainSupplierTrigger && !isG1OnsiteFulfillmentMode && !isMultiSupplierMode) {
        if (purchaseItems.length > 0) {
            const allCostsEntered = purchaseItems.every(item => {
                return item.unit_cost !== undefined && item.unit_cost !== '' && !isNaN(parseFloat(item.unit_cost));
            });
            if (allCostsEntered) {
                cost = purchaseItems.reduce((total, item) => {
                    const itemCostNum = parseFloat(item.unit_cost);
                    const quantityNum = parseInt(item.quantity, 10);
                    return total + (itemCostNum * quantityNum);
                }, 0);
                isCalculable = true;
            }
        } else { 
            isCalculable = true; 
            cost = 0;
        }
    }
    
    if (!revenue && originalLineItems.length === 0 && orderStatus !== 'processed') {
        isCalculable = false;
    }
    if (revenue === 0 && orderStatus === 'processed' && originalLineItems.length === 0) {
        isCalculable = true;
        cost = 0;
    }

    setProfitInfo(currentProfitInfo => {
        let shouldUpdate = false;
        if (currentProfitInfo.isCalculable !== isCalculable) shouldUpdate = true;
        if (currentProfitInfo.totalRevenue !== revenue) shouldUpdate = true;
        if (isCalculable && currentProfitInfo.totalCost !== cost) shouldUpdate = true;
        if (!isCalculable && currentProfitInfo.isCalculable) shouldUpdate = true;

        if (shouldUpdate) {
            if (isCalculable) {
                const profit = revenue - cost;
                const margin = revenue > 0 ? (profit / revenue) * 100 : 0; 
                return {
                    totalRevenue: revenue,
                    totalCost: cost,
                    profitAmount: profit,
                    profitMargin: margin,
                    isCalculable: true
                };
            } else {
                return { 
                    totalRevenue: revenue, 
                    totalCost: 0, 
                    profitAmount: 0, 
                    profitMargin: 0, 
                    isCalculable: false 
                };
            }
        }
        return currentProfitInfo; 
    });

  }, [
      orderData, 
      purchaseItems, 
      multiSupplierItemCosts, 
      isMultiSupplierMode, 
      isG1OnsiteFulfillmentMode, 
      selectedMainSupplierTrigger, 
      lineItemAssignments,
      originalLineItems 
  ]);


  useEffect(() => {
    if (!currentUser || !orderData?.line_items || orderData.line_items.length === 0 || !apiService) return;
    const fetchAllSpares = async () => {
        setLoadingSpares(true);
        const sparesMap = {};
        for (const item of orderData.line_items) {
            if (item.original_sku && item.hpe_pn_type === 'option') {
                try {
                    const trimmedOriginalSku = String(item.original_sku).trim();
                    if (!trimmedOriginalSku) continue;
                    const spareData = await apiService.get(`/lookup/spare_part/${encodeURIComponent(trimmedOriginalSku)}`);
                    if (spareData.spare_sku) sparesMap[item.line_item_id] = String(spareData.spare_sku).trim();
                } catch (err) {
                    if (err.status !== 404) console.error(`Spare lookup exception for ${item.original_sku}:`, err);
                }
            }
        }
        setLineItemSpares(sparesMap); setLoadingSpares(false);
    };
    fetchAllSpares();
  }, [orderData?.line_items, currentUser, apiService]);

  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  useEffect(() => {
    if (!currentUser || !debouncedSku || skuToLookup.index === -1 || isMultiSupplierMode || isG1OnsiteFulfillmentMode || !apiService) return;
    const abortController = new AbortController();
    const fetchDescription = async () => {
      try {
        const data = await apiService.get(`/lookup/description/${encodeURIComponent(String(debouncedSku).trim())}`);
        if (abortController.signal.aborted) return;
        setPurchaseItems(prevItems => {
            const updatedItems = [...prevItems];
            if (updatedItems[skuToLookup.index]?.skuInputValue === debouncedSku) {
                let newDescription = data.description;
                if (newDescription && typeof newDescription === 'string' && !newDescription.endsWith(cleanPullSuffix)) {
                    newDescription += cleanPullSuffix;
                } else if (!newDescription) {
                    const existingDesc = (updatedItems[skuToLookup.index].description || "").replace(new RegExp(escapeRegExp(cleanPullSuffix) + "$"), "").trim();
                    newDescription = (existingDesc ? existingDesc + " " : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(" " + cleanPullSuffix.trim())) {
                        newDescription = cleanPullSuffix.trim();
                    }
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
            }
            return updatedItems;
        });
      } catch (error) {
        if (error.name !== 'AbortError' && error.status !== 401 && error.status !== 403) {
            console.error("Error fetching description:", error);
        } else if (error.status === 401 || error.status === 403) {
            console.error("Unauthorized to fetch SKU description.");
        }
      }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, currentUser, isMultiSupplierMode, isG1OnsiteFulfillmentMode, apiService]);

  const handleMainSupplierTriggerChange = (e) => {
    const value = e.target.value;
    setSelectedMainSupplierTrigger(value);
    setProcessError(null); setProcessSuccess(false);
    setProcessSuccessMessage(''); setProcessedPOsInfo([]);

    let defaultMethodForThisMode = 'UPS Ground';

    if (orderData?.order) {
        const orderDetails = orderData.order;
        if (orderDetails.is_bill_to_customer_account && orderDetails.customer_selected_freight_service) {
            const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_freight_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'ups');
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
            }
        } else if (orderDetails.is_bill_to_customer_fedex_account && orderDetails.customer_selected_fedex_service) {
            const customerSelectedService = formatShippingMethod(orderDetails.customer_selected_fedex_service);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === customerSelectedService && opt.carrier === 'fedex');
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
            }
        } else if (orderDetails.customer_shipping_method) {
            const parsedOrderMethod = formatShippingMethod(orderDetails.customer_shipping_method);
            const matchedOption = SHIPPING_METHODS_OPTIONS.find(opt => opt.value === parsedOrderMethod);
            if (matchedOption) {
                defaultMethodForThisMode = matchedOption.value;
            }
        }
    }
    setOriginalCustomerShippingMethod(defaultMethodForThisMode);
    setShipmentMethod(defaultMethodForThisMode);
    setShipmentWeight('');
    setIsBlindDropShip(false);

    const newSelectedOption = getSelectedShippingOption(defaultMethodForThisMode);
    if (newSelectedOption.carrier === 'ups' && orderData?.order?.is_bill_to_customer_account) {
        setBillToCustomerUps(true);
        setCustomerUpsAccountNumber(orderData.order.customer_ups_account_number || '');
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
    } else if (newSelectedOption.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account) {
        setBillToCustomerFedex(true);
        setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number || '');
        setBillToCustomerUps(false);
        setCustomerUpsAccountNumber('');
    } else {
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
        setBillToCustomerUps(false);
        setCustomerUpsAccountNumber('');
    }


    if (value === G1_ONSITE_FULFILLMENT_VALUE) {
        setIsG1OnsiteFulfillmentMode(true); setIsMultiSupplierMode(false);
        setSingleOrderPoNotes('');
        setPurchaseItems([]);
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({});
        setMultiSupplierShipmentDetails({});
    } else if (value === MULTI_SUPPLIER_MODE_VALUE) {
        setIsG1OnsiteFulfillmentMode(false); setIsMultiSupplierMode(true);
        setSingleOrderPoNotes('');
        setPurchaseItems([]);
        const initialMultiDesc = {};
        const currentOriginalLineItems = orderData?.line_items || []; 
        if (currentOriginalLineItems) {
            currentOriginalLineItems.forEach(item => {
                let defaultDescription = item.hpe_po_description || item.line_item_name || '';
                if (defaultDescription && !defaultDescription.endsWith(cleanPullSuffix)) defaultDescription += cleanPullSuffix;
                else if (!defaultDescription && item.original_sku) defaultDescription = `${item.original_sku}${cleanPullSuffix}`;
                initialMultiDesc[item.line_item_id] = defaultDescription;
            });
        }
        setMultiSupplierItemDescriptions(initialMultiDesc);
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({});
        const newMultiShipDetails = {};
        const initialShipOptionForMulti = getSelectedShippingOption(originalCustomerShippingMethod);
        Object.keys(lineItemAssignments).forEach(itemId => { 
            const supId = lineItemAssignments[itemId];
            if (supId && !newMultiShipDetails[supId]) {
                newMultiShipDetails[supId] = {
                    method: originalCustomerShippingMethod,
                    weight: '',
                    billToCustomerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && orderData?.order?.is_bill_to_customer_account,
                    customerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && orderData?.order?.is_bill_to_customer_account ? (orderData.order.customer_ups_account_number || '') : '',
                    billToCustomerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account,
                    customerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account ? (orderData.order.customer_fedex_account_number || '') : ''
                };
            }
        });
        setMultiSupplierShipmentDetails(newMultiShipDetails);
    } else { 
        setIsG1OnsiteFulfillmentMode(false); setIsMultiSupplierMode(false);
        const s = suppliers.find(sup => sup.id === parseInt(value, 10));
        setSingleOrderPoNotes(s?.defaultponotes || '');
        const currentOriginalLineItems = orderData?.line_items || []; 
        if (currentOriginalLineItems) {
            const initialItemsForPoForm = currentOriginalLineItems.map(item => ({
                original_order_line_item_id: item.line_item_id, sku: item.hpe_option_pn || item.original_sku || '',
                description: (item.hpe_po_description || item.line_item_name || '') + ( (item.hpe_po_description || item.line_item_name || '').endsWith(cleanPullSuffix) ? '' : cleanPullSuffix),
                skuInputValue: item.hpe_option_pn || item.original_sku || '', quantity: item.quantity || 1, unit_cost: '', condition: 'New',
                original_sku: item.original_sku, hpe_option_pn: item.hpe_option_pn, original_name: item.line_item_name,
                hpe_po_description: item.hpe_po_description, hpe_pn_type: item.hpe_pn_type,
            }));
            setPurchaseItems(initialItemsForPoForm);
        } else {
            setPurchaseItems([]);
        }
        setLineItemAssignments({}); setPoNotesBySupplier({});
        setMultiSupplierItemCosts({}); setMultiSupplierItemDescriptions({});
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
        const initialShipOptionForMulti = getSelectedShippingOption(originalCustomerShippingMethod);
        setMultiSupplierShipmentDetails(prev => ({
            ...prev,
            [supplierId]: {
                method: originalCustomerShippingMethod,
                weight: '',
                billToCustomerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && orderData?.order?.is_bill_to_customer_account,
                customerUpsAccount: initialShipOptionForMulti.carrier === 'ups' && orderData?.order?.is_bill_to_customer_account ? (orderData.order.customer_ups_account_number || '') : '',
                billToCustomerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account,
                customerFedexAccount: initialShipOptionForMulti.carrier === 'fedex' && orderData?.order?.is_bill_to_customer_fedex_account ? (orderData.order.customer_fedex_account_number || '') : ''
            }
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
    setMultiSupplierShipmentDetails(prev => {
        const currentDetails = prev[supplierId] || { method: originalCustomerShippingMethod, weight: '' };
        const newDetailsForSupplier = { ...currentDetails, [field]: value };

        if (field === 'method') {
            const selectedOpt = getSelectedShippingOption(value);
            if (selectedOpt?.carrier === 'ups') {
                newDetailsForSupplier.billToCustomerUpsAccount = orderData?.order?.is_bill_to_customer_account || false;
                newDetailsForSupplier.customerUpsAccount = (orderData?.order?.is_bill_to_customer_account && orderData?.order?.customer_ups_account_number) ? orderData.order.customer_ups_account_number : '';
                newDetailsForSupplier.billToCustomerFedexAccount = false;
                newDetailsForSupplier.customerFedexAccount = '';
            } else if (selectedOpt?.carrier === 'fedex') {
                newDetailsForSupplier.billToCustomerFedexAccount = orderData?.order?.is_bill_to_customer_fedex_account || false;
                newDetailsForSupplier.customerFedexAccount = (orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) ? orderData.order.customer_fedex_account_number : '';
                newDetailsForSupplier.billToCustomerUpsAccount = false;
                newDetailsForSupplier.customerUpsAccount = '';
            } else { 
                newDetailsForSupplier.billToCustomerUpsAccount = false;
                newDetailsForSupplier.customerUpsAccount = '';
                newDetailsForSupplier.billToCustomerFedexAccount = false;
                newDetailsForSupplier.customerFedexAccount = '';
            }
        }
        return { ...prev, [supplierId]: newDetailsForSupplier };
    });
};


  const handlePurchaseItemChange = (index, field, value) => {
    setPurchaseItems(prevItems => {
        const items = [...prevItems];
        if (items[index]) {
            items[index] = { ...items[index], [field]: value };
            if (field === 'skuInputValue') {
                const trimmedSku = String(value).trim();
                items[index].skuInputValue = trimmedSku;
                items[index].sku = trimmedSku;
                setSkuToLookup({ index, sku: trimmedSku });
            }
        }
        return items;
    });
  };

  const handleShipmentMethodChange = (e) => {
    const newMethod = e.target.value;
    setShipmentMethod(newMethod);
    const selectedOpt = getSelectedShippingOption(newMethod);

    if (selectedOpt?.carrier === 'ups') {
        setBillToCustomerUps(orderData?.order?.is_bill_to_customer_account || false);
        setCustomerUpsAccountNumber((orderData?.order?.is_bill_to_customer_account && orderData?.order?.customer_ups_account_number) ? orderData.order.customer_ups_account_number : '');
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
    } else if (selectedOpt?.carrier === 'fedex') {
        setBillToCustomerFedex(orderData?.order?.is_bill_to_customer_fedex_account || false);
        setCustomerFedexAccountNumber((orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) ? orderData.order.customer_fedex_account_number : '');
        setBillToCustomerUps(false);
        setCustomerUpsAccountNumber('');
    } else {
        setBillToCustomerFedex(false);
        setCustomerFedexAccountNumber('');
        setBillToCustomerUps(false);
        setCustomerUpsAccountNumber('');
    }
  };
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
    if (orderData?.order?.bigcommerce_order_id) {
        await handleCopyToClipboard(orderData.order.bigcommerce_order_id);
    }
    if (!currentUser || !apiService) {
        setStatusUpdateMessage("Please log in to perform this action or API service is unavailable.");
        return;
    }
    const currentOrderStatus = orderData?.order?.status?.toLowerCase();
    const trimmedPartNumberForStatusCheck = String(partNumber || '').trim();
    if (currentOrderStatus === 'new' && trimmedPartNumberForStatusCheck) {
      try {
        setStatusUpdateMessage('');
        await apiService.post(`/orders/${orderId}/status`, { status: 'RFQ Sent' });
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, false);
        setStatusUpdateMessage(`Status updated to RFQ Sent for part: ${trimmedPartNumberForStatusCheck}`);
      } catch (err) {
        let errorMsg = err.data?.message || err.message || `Error updating status for part ${trimmedPartNumberForStatusCheck}`;
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setStatusUpdateMessage(errorMsg);
      }
    }
    const brokerbinUrl = createBrokerbinLink(partNumber);
    window.open(brokerbinUrl, '_blank', 'noopener,noreferrer');
  };

  const handleManualStatusUpdate = async (newStatus) => {
    if (!currentUser || !apiService) { setStatusUpdateMessage("Please log in or API service unavailable."); return; }
    if (!orderId) { setStatusUpdateMessage("Order ID missing."); return; }
    setManualStatusUpdateInProgress(true); setStatusUpdateMessage('');
    try {
        await apiService.post(`/orders/${orderId}/status`, { status: newStatus });
        setStatusUpdateMessage(`Order status successfully updated to '${newStatus}'.`);
        const ac = new AbortController(); await fetchOrderAndSuppliers(ac.signal, false);
    } catch (err) {
        let errorMsg = err.data?.message || err.message || "Error updating status.";
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setStatusUpdateMessage(errorMsg);
    } finally { setManualStatusUpdateInProgress(false); }
  };

  const handleProcessOrder = async (e) => {
    e.preventDefault();
    if (!currentUser || !apiService) { setProcessError("Please log in or API service unavailable."); return; }
    setProcessing(true); setProcessError(null); setProcessSuccess(false);
    setProcessSuccessMessage(''); setProcessedPOsInfo([]); setStatusUpdateMessage('');

    let payloadAssignments = [];
    const currentOriginalLineItems = orderData?.line_items || []; 

    if (isG1OnsiteFulfillmentMode) {
        if (currentOriginalLineItems.length > 0) {
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight for G1 Onsite Fulfillment."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShippingOption) { setProcessError("Please select a shipment method for G1 Onsite Fulfillment."); setProcessing(false); return; }
            if (currentSelectedShippingOption.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setProcessError("Customer FedEx Account Number is required for G1 Onsite Bill Recipient (FedEx)."); setProcessing(false); return;
            }
            if (currentSelectedShippingOption.carrier === 'ups' && billToCustomerUps && !customerUpsAccountNumber.trim()) {
                setProcessError("Customer UPS Account Number is required for G1 Onsite Bill Recipient (UPS)."); setProcessing(false); return;
            }
        }
        payloadAssignments.push({
            supplier_id: G1_ONSITE_FULFILLMENT_VALUE,
            payment_instructions: "G1 Onsite Fulfillment",
            po_line_items: [],
            total_shipment_weight_lbs: currentOriginalLineItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null,
            shipment_method: currentOriginalLineItems.length > 0 ? shipmentMethod : null,
            carrier: currentOriginalLineItems.length > 0 ? (currentSelectedShippingOption?.carrier || null) : null,
            is_bill_to_customer_fedex_account: currentOriginalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' ? billToCustomerFedex : false,
            customer_fedex_account_number: currentOriginalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
            is_bill_to_customer_ups_account: currentOriginalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' ? billToCustomerUps : false,
            customer_ups_account_number: currentOriginalLineItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' && billToCustomerUps ? customerUpsAccountNumber.trim() : null,
            is_blind_drop_ship: isBlindDropShip
        });
    } else if (isMultiSupplierMode) {
        const assignedSupplierIds = [...new Set(Object.values(lineItemAssignments))].filter(id => id);
        if (currentOriginalLineItems.length > 0) {
             if (assignedSupplierIds.length === 0) { setProcessError("Multi-Supplier Mode: Assign items to at least one supplier."); setProcessing(false); return; }
             if (!currentOriginalLineItems.every(item => !!lineItemAssignments[item.line_item_id])) { setProcessError("Multi-Supplier Mode: Assign all original items to a supplier."); setProcessing(false); return; }
        }

        for (const supId of assignedSupplierIds) {
            const supplier = suppliers.find(s => s.id === parseInt(supId, 10));
            const itemsForThisSupplier = currentOriginalLineItems.filter(item => lineItemAssignments[item.line_item_id] === supId);
            if (itemsForThisSupplier.length > 0) {
                let itemCostValidationError = null;
                const poLineItems = itemsForThisSupplier.map(item => {
                    const costStr = multiSupplierItemCosts[item.line_item_id]; const costFloat = parseFloat(costStr);
                    if (costStr === undefined || costStr === '' || isNaN(costFloat) || costFloat < 0) { itemCostValidationError = `Missing/invalid unit cost for SKU ${item.original_sku || 'N/A'} (Supplier: ${supplier?.name}).`; return null; }
                    let descriptionForPo = multiSupplierItemDescriptions[item.line_item_id];
                    if (descriptionForPo === undefined) descriptionForPo = item.hpe_po_description || item.line_item_name || `${item.original_sku || ''}${cleanPullSuffix}`;
                    if (!String(descriptionForPo).trim()) { itemCostValidationError = `Missing description for SKU ${item.original_sku || 'N/A'} (Supplier: ${supplier?.name}).`; return null; }
                    return { original_order_line_item_id: item.line_item_id, sku: item.hpe_option_pn || item.original_sku, description: String(descriptionForPo).trim(), quantity: item.quantity, unit_cost: costFloat.toFixed(2), condition: 'New' };
                }).filter(Boolean);

                if (itemCostValidationError) { setProcessError(itemCostValidationError); setProcessing(false); return; }
                if (poLineItems.length !== itemsForThisSupplier.length && itemsForThisSupplier.length > 0) { setProcessError("One or more items for a supplier had validation errors."); setProcessing(false); return; }

                const shipmentDetailsForThisPo = multiSupplierShipmentDetails[supId] || {};
                const currentPoMethod = shipmentDetailsForThisPo.method;
                const currentPoWeight = shipmentDetailsForThisPo.weight;
                const currentSelectedShipOptionMulti = getSelectedShippingOption(currentPoMethod);

                if (currentPoMethod && (!currentPoWeight || parseFloat(currentPoWeight) <= 0)) { setProcessError(`Invalid/missing weight for PO to ${supplier?.name}.`); setProcessing(false); return; }
                if (!currentPoMethod && currentPoWeight && parseFloat(currentPoWeight) > 0) { setProcessError(`Shipping method required for PO to ${supplier?.name}.`); setProcessing(false); return; }

                const isFedexBillRecipientMulti = shipmentDetailsForThisPo.billToCustomerFedexAccount || false;
                const fedexAccountNumMulti = shipmentDetailsForThisPo.customerFedexAccount || '';
                const isUpsBillRecipientMulti = shipmentDetailsForThisPo.billToCustomerUpsAccount || false;
                const upsAccountNumMulti = shipmentDetailsForThisPo.customerUpsAccount || '';

                if (currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti && !fedexAccountNumMulti.trim()) {
                    setProcessError(`Customer FedEx Account Number is required for PO to ${supplier?.name} when 'Bill to Customer' is checked.`); setProcessing(false); return;
                }
                if (currentSelectedShipOptionMulti?.carrier === 'ups' && isUpsBillRecipientMulti && !upsAccountNumMulti.trim()) {
                    setProcessError(`Customer UPS Account Number is required for PO to ${supplier?.name} when 'Bill to Customer' is checked.`); setProcessing(false); return;
                }

                payloadAssignments.push({
                    supplier_id: parseInt(supId, 10),
                    payment_instructions: poNotesBySupplier[supId] || "",
                    po_line_items: poLineItems,
                    total_shipment_weight_lbs: currentPoWeight ? parseFloat(currentPoWeight).toFixed(1) : null,
                    shipment_method: currentPoMethod || null,
                    carrier: currentSelectedShipOptionMulti?.carrier || (currentPoMethod ? null : null),
                    is_bill_to_customer_fedex_account: currentSelectedShipOptionMulti?.carrier === 'fedex' ? isFedexBillRecipientMulti : false,
                    customer_fedex_account_number: currentSelectedShipOptionMulti?.carrier === 'fedex' && isFedexBillRecipientMulti ? fedexAccountNumMulti.trim() : null,
                    is_bill_to_customer_ups_account: currentSelectedShipOptionMulti?.carrier === 'ups' ? isUpsBillRecipientMulti : false,
                    customer_ups_account_number: currentSelectedShipOptionMulti?.carrier === 'ups' && isUpsBillRecipientMulti ? upsAccountNumMulti.trim() : null,
                    is_blind_drop_ship: isBlindDropShip
                });
            }
        }
        if (payloadAssignments.length === 0 && currentOriginalLineItems.length > 0) { setProcessError("No items assigned for PO generation in multi-supplier mode."); setProcessing(false); return; }

    } else { // Single Supplier Mode
        const singleSelectedSupId = selectedMainSupplierTrigger;
        if (!singleSelectedSupId || singleSelectedSupId === MULTI_SUPPLIER_MODE_VALUE || singleSelectedSupId === G1_ONSITE_FULFILLMENT_VALUE) {
            setProcessError("Please select a supplier."); setProcessing(false); return;
        }
        const currentPurchaseItems = purchaseItems; 

        if (currentPurchaseItems.length > 0) {
            const weightFloat = parseFloat(shipmentWeight);
            if (!shipmentWeight || isNaN(weightFloat) || weightFloat <= 0) { setProcessError("Invalid shipment weight."); setProcessing(false); return; }
            if (!shipmentMethod || !currentSelectedShippingOption) { setProcessError("Please select a shipment method."); setProcessing(false); return; }
            if (currentSelectedShippingOption.carrier === 'fedex' && billToCustomerFedex && !customerFedexAccountNumber.trim()) {
                setProcessError("Customer FedEx Account Number is required when 'Bill to Customer' (FedEx) is checked."); setProcessing(false); return;
            }
            if (currentSelectedShippingOption.carrier === 'ups' && billToCustomerUps && !customerUpsAccountNumber.trim()) {
                setProcessError("Customer UPS Account Number is required when 'Bill to Customer' (UPS) is checked."); setProcessing(false); return;
            }
        }

        let itemValidationError = null;
        const finalPurchaseItems = currentPurchaseItems.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10); const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `Item #${index + 1}: Quantity > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `Item #${index + 1}: Unit cost invalid.`; return null; }
            if (!String(item.skuInputValue).trim()) { itemValidationError = `Item #${index + 1}: SKU required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `Item #${index + 1}: Description required.`; return null; }
            return { original_order_line_item_id: item.original_order_line_item_id, sku: String(item.skuInputValue).trim(), description: String(item.description).trim(), quantity: quantityInt, unit_cost: costFloat.toFixed(2), condition: item.condition || 'New' };
        }).filter(Boolean);

        if (itemValidationError) { setProcessError(itemValidationError); setProcessing(false); return; }
        if (finalPurchaseItems.length === 0 && currentOriginalLineItems.length > 0) { setProcessError("No valid line items for PO."); setProcessing(false); return; }

        if (finalPurchaseItems.length > 0 || currentOriginalLineItems.length === 0) { 
            payloadAssignments.push({
                supplier_id: parseInt(singleSelectedSupId, 10),
                payment_instructions: singleOrderPoNotes,
                total_shipment_weight_lbs: finalPurchaseItems.length > 0 ? parseFloat(shipmentWeight).toFixed(1) : null,
                shipment_method: finalPurchaseItems.length > 0 ? shipmentMethod : null,
                po_line_items: finalPurchaseItems,
                carrier: finalPurchaseItems.length > 0 ? (currentSelectedShippingOption?.carrier || null) : null,
                is_bill_to_customer_fedex_account: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' ? billToCustomerFedex : false,
                customer_fedex_account_number: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'fedex' && billToCustomerFedex ? customerFedexAccountNumber.trim() : null,
                is_bill_to_customer_ups_account: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' ? billToCustomerUps : false,
                customer_ups_account_number: finalPurchaseItems.length > 0 && currentSelectedShippingOption?.carrier === 'ups' && billToCustomerUps ? customerUpsAccountNumber.trim() : null,
                is_blind_drop_ship: isBlindDropShip
            });
        }
    }

    if (payloadAssignments.length === 0 && currentOriginalLineItems.length > 0 && !isG1OnsiteFulfillmentMode) { setProcessError("No data for POs. Check assignments/details."); setProcessing(false); return; }
    if (payloadAssignments.length === 0 && currentOriginalLineItems.length === 0 && selectedMainSupplierTrigger === "") { setProcessError("Select supplier/mode."); setProcessing(false); return; }


    try {
        const finalPayload = { assignments: payloadAssignments };
        const responseData = await apiService.post(`/orders/${orderId}/process`, finalPayload);
        setProcessSuccess(true);
        setProcessSuccessMessage(responseData.message || "Order processed successfully!");
        setProcessedPOsInfo(Array.isArray(responseData.processed_purchase_orders) ? responseData.processed_purchase_orders : []);
        const ac = new AbortController();
        await fetchOrderAndSuppliers(ac.signal, true);
    } catch (err) {
        let errorMsg = err.data?.error || err.data?.message || err.message || "Unexpected error during processing.";
        if (err.status === 401 || err.status === 403) { errorMsg = "Unauthorized. Please log in again."; navigate('/login'); }
        setProcessError(errorMsg);
        setProcessSuccess(false); setProcessedPOsInfo([]);
    } finally { setProcessing(false); }
  };

  if (authLoading) return <div className="loading-message">Loading session...</div>;
  if (!currentUser && !authLoading) return <div className="order-detail-container" style={{ textAlign: 'center', marginTop: '50px' }}><h2>Order Details</h2><p className="error-message">Please <Link to="/login">log in</Link>.</p></div>;
  if (loading && !orderData && !processSuccess) return <div className="loading-message">Loading order details...</div>;
  if (error && !loading) return <div className="error-message" style={{ margin: '20px', padding: '20px', border: '1px solid red' }}>Error: {error}</div>;

  const order = orderData?.order;
  const orderStatus = orderData?.order?.status?.toLowerCase(); 

  if (!order && !processSuccess && !loading) {
      return <p style={{ textAlign: 'center', marginTop: '20px' }}>Order details not found or error loading.</p>;
  }

  const isActuallyProcessed = orderStatus === 'processed' || orderStatus === 'completed offline';
  const canDisplayProcessingForm = !processSuccess && !isActuallyProcessed;
  const disableAllActions = processing || manualStatusUpdateInProgress;
  const disableEditableFormFields = isActuallyProcessed || disableAllActions || processSuccess;

  let displayOrderDate = 'N/A';
  if (order?.order_date) try { displayOrderDate = new Date(order.order_date).toLocaleDateString(); } catch (e) { /* ignore */ }

  const displayShipMethodInOrderInfo = formatShippingMethod(
    (order?.is_bill_to_customer_account && order?.customer_selected_freight_service) 
        ? order.customer_selected_freight_service
        : (order?.is_bill_to_customer_fedex_account && order?.customer_selected_fedex_service) 
            ? order.customer_selected_fedex_service
            : order?.customer_shipping_method 
  );


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
          <div className="dashboard-link-container" style={{ marginTop: 'var(--spacing-md)', marginBottom: 'var(--spacing-lg)', textAlign: 'center' }}>
            <a
              href="https://store-g6oxherh18.mybigcommerce.com/manage/orders"
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-info"
            >
              G1 BC Order Dashboard
            </a>
          </div>
          {processSuccessMessage && (
            <p className="success-message-detail" style={{textAlign: 'center', marginBottom: 'var(--spacing-lg)'}}>{processSuccessMessage}</p>
          )}
           {/* Display Profitability Analysis if the order was just successfully processed and not G1 Onsite */}
           {!isG1OnsiteFulfillmentMode && profitInfo.isCalculable && (
             <ProfitDisplay info={profitInfo} />
           )}
        </div>
      )}

      {/* MODIFIED: Show ProfitDisplay for already "Processed" orders (and not G1 Onsite) */}
      {orderStatus === 'processed' && !processSuccess && !isG1OnsiteFulfillmentMode && profitInfo.isCalculable && (
        <ProfitDisplay info={profitInfo} />
      )}


      {orderData?.order?.status?.toLowerCase() === 'rfq sent' && orderData?.order?.bigcommerce_order_id && !isActuallyProcessed && !processSuccess && (
        <section className="see-quotes-gmail-card card">
         <div className="button-container-center">
            <button
              onClick={handleSeeQuotesClick}
              className="btn btn-primary"
              disabled={processing || manualStatusUpdateInProgress}
            >
              View Supplier Quotes Received
            </button>
          </div>
          {seeQuotesStatus && (
            <p className={`clipboard-status ${seeQuotesStatus.toLowerCase().includes('error') ? 'error-message-inline' : 'success-message-inline'} centered-status-message`}>
              {seeQuotesStatus}
            </p>
          )}
        </section>
      )}

      {orderData && order && !processSuccess && !isActuallyProcessed && (
       <section className="order-info card">
        <h3>Order Information</h3>
        <div><strong>Rec'd:</strong> {displayOrderDate}</div>
        <div><strong>Customer:</strong> {order.customer_company || order.customer_name || 'N/A'}</div>
        <div><strong>Paid by:</strong> {order.payment_method || 'N/A'}</div>
        <div><strong>Ship via:</strong> {displayShipMethodInOrderInfo}</div>
        <div><strong>Ship to:</strong> {order.customer_shipping_city || 'N/A'}, {order.customer_shipping_state || 'N/A'}</div>

        {order.is_bill_to_customer_account && order.customer_ups_account_number && (
          <div className="customer-ups-account-info" style={{backgroundColor: 'var(--info-bg,rgb(255, 0, 0))', color: 'var(--info-text,rgb(255, 255, 255))', border: '1px dashed var(--info-border, #b3e0ff)', opacity: '60%'}}>
            <strong>Bill Shipping To:</strong> Customer UPS Acct # {order.customer_ups_account_number}
            {order.customer_selected_freight_service && ` (Service: ${formatShippingMethod(order.customer_selected_freight_service)})`}
            {order.customer_ups_account_zipcode && ` (Zip: ${order.customer_ups_account_zipcode})`}
          </div>
        )}
         {order.is_bill_to_customer_fedex_account && order.customer_fedex_account_number && (
          <div className="customer-ups-account-info" style={{backgroundColor: 'var(--info-bg-alt,rgb(255, 0, 0))', color: 'var(--info-text-alt,rgb(255, 255, 255))', border: '1px dashed var(--info-border-alt, #b3ffcc)', opacity: '60%'}}>
            <strong>Bill Shipping To:</strong> Customer FedEx Acct # {order.customer_fedex_account_number}
            {order.customer_selected_fedex_service && ` (Service: ${formatShippingMethod(order.customer_selected_fedex_service)})`}
          </div>
        )}


        {order.customer_notes && (<div style={{ marginTop: '5px' }}><strong>Comments:</strong> {order.customer_notes}</div>)}
        <hr style={{ margin: '10px 0' }} />
        {(orderData?.line_items || []).map((item) => (
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
        <h3>Order Fulfillment</h3>
        <div className="form-grid">
            <label htmlFor="mainSupplierTrigger" style={{ marginRight: '8px' }}>Initiate Fulfillment Strategy:</label>
            <select
                id="mainSupplierTrigger"
                value={selectedMainSupplierTrigger}
                onChange={handleMainSupplierTriggerChange}
                disabled={disableAllActions || (suppliers.length === 0 && (orderData?.line_items || []).length === 0) }
                style={{ flexGrow: 1 }}
            >
                <option value="">-- Select Supplier --</option>
                {(suppliers || []).map(supplier => (
                    <option key={supplier.id} value={supplier.id}>
                        {supplier.name || 'Unnamed Supplier'}
                    </option>
                ))}
                {(orderData?.line_items || []).length > 1 && (
                    <option value={MULTI_SUPPLIER_MODE_VALUE}>** Use Multiple Suppliers **</option>
                )}
                {(orderData?.line_items || []).length > 0 && (
                   <option value={G1_ONSITE_FULFILLMENT_VALUE}>G1 Onsite Fulfillment</option>
                )}
            </select>
        </div>
      </section>
     )}

      {/* Form for Single Regular Supplier PO */}
      {canDisplayProcessingForm && !isMultiSupplierMode && !isG1OnsiteFulfillmentMode && selectedMainSupplierTrigger &&
       selectedMainSupplierTrigger !== MULTI_SUPPLIER_MODE_VALUE && selectedMainSupplierTrigger !== G1_ONSITE_FULFILLMENT_VALUE && (
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
                        <div>
                            <label className="mobile-label" htmlFor={`sku-${index}`}>SKU:</label>
                            <input id={`sku-${index}`} type="text" value={item.skuInputValue || ''} onChange={(e) => handlePurchaseItemChange(index, 'skuInputValue', e.target.value)} placeholder="SKU" required disabled={disableEditableFormFields} title={item.original_sku ? `Original: ${item.original_sku}` : ''} className="sku-input" />
                        </div>
                        <div>
                            <label className="mobile-label" htmlFor={`desc-${index}`}>Desc:</label>
                            <textarea id={`desc-${index}`} value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableEditableFormFields} className="description-textarea" />
                        </div>
                        <div className="qty-cost-row">
                            <div>
                                <label className="mobile-label" htmlFor={`qty-${index}`}>Qty:</label>
                                <input id={`qty-${index}`} type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableEditableFormFields} className="qty-input" />
                            </div>
                            <div>
                                <label className="mobile-label" htmlFor={`cost-${index}`}>Cost:</label>
                                <input id={`cost-${index}`} type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableEditableFormFields} className="price-input" />
                            </div>
                        </div>
                    </div>
                ))}
              </div>
            </section>
            <section className="shipment-info card">
              <h3>Shipment Information</h3>
              <div className="form-grid">
                <label htmlFor="shipmentMethodSingle">Method:</label>
                <select
                  id="shipmentMethodSingle"
                  value={shipmentMethod}
                  onChange={handleShipmentMethodChange}
                  disabled={disableEditableFormFields}
                  required={(orderData?.line_items || []).length > 0 && !isG1OnsiteFulfillmentMode && purchaseItems.length > 0}
                >
                    {SHIPPING_METHODS_OPTIONS.map((opt, index) => <option key={`${opt.value}-${opt.carrier}-single-${index}`} value={opt.value}>{opt.label}</option>)}
                </select>

                <label htmlFor="shipmentWeightSingle">Weight (lbs):</label>
                <input
                    type="number"
                    id="shipmentWeightSingle"
                    className="weight-input-field"
                    value={shipmentWeight}
                    onChange={handleShipmentWeightChange}
                    step="0.1" min="0.1"
                    placeholder="e.g., 5.0"
                    required={(orderData?.line_items || []).length > 0 && !isG1OnsiteFulfillmentMode && purchaseItems.length > 0}
                    disabled={disableEditableFormFields}
                />

                {currentSelectedShippingOption?.carrier === 'fedex' && (
                <>
                    <label htmlFor="billToCustomerFedexSingle">Bill Customer FedEx:</label>
                    <input
                        type="checkbox"
                        id="billToCustomerFedexSingle"
                        checked={billToCustomerFedex}
                        onChange={(e) => {
                            setBillToCustomerFedex(e.target.checked);
                            if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number);
                            } else if (!e.target.checked) {
                                setCustomerFedexAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                    />

                    {billToCustomerFedex && (
                    <>
                        <label htmlFor="customerFedexAccountSingle">Customer FedEx Acct #:</label>
                        <input
                            type="text"
                            id="customerFedexAccountSingle"
                            value={customerFedexAccountNumber}
                            onChange={(e) => setCustomerFedexAccountNumber(e.target.value)}
                            placeholder="FedEx Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                    </>
                    )}
                </>
               )}
               {currentSelectedShippingOption?.carrier === 'ups' && (
                <>
                    <label htmlFor="billToCustomerUpsSingle">Bill Customer UPS:</label>
                    <input
                        type="checkbox"
                        id="billToCustomerUpsSingle"
                        checked={billToCustomerUps}
                        onChange={(e) => {
                            setBillToCustomerUps(e.target.checked);
                            if (e.target.checked && orderData?.order?.is_bill_to_customer_account && orderData?.order?.customer_ups_account_number) {
                                setCustomerUpsAccountNumber(orderData.order.customer_ups_account_number);
                            } else if (!e.target.checked) {
                                setCustomerUpsAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                    />
                    {billToCustomerUps && (
                    <>
                        <label htmlFor="customerUpsAccountSingle">Customer UPS Acct #:</label>
                        <input
                            type="text"
                            id="customerUpsAccountSingle"
                            value={customerUpsAccountNumber}
                            onChange={(e) => setCustomerUpsAccountNumber(e.target.value)}
                            placeholder="UPS Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                    </>
                    )}
                </>
               )}
              </div>
            </section>

            <section className="branding-options-section card" style={{ marginTop: 'var(--spacing-lg)' }}>
                <h3>Branding Options</h3>
                <div className="form-grid"> 
                    <label htmlFor="brandingOptionSingle">Branding:</label>
                    <select
                        id="brandingOptionSingle"
                        value={isBlindDropShip ? 'blind' : 'g1'}
                        onChange={handleBrandingChange}
                        disabled={disableEditableFormFields}
                    >
                        <option value="g1">Global One Technology Branding</option>
                        <option value="blind">Blind Ship (Generic Packing Slip)</option>
                    </select>
                </div>
            </section>   

            <ProfitDisplay info={profitInfo} />
           
             <div className="order-actions">
                <button type="submit" disabled={disableAllActions || processing} className="process-order-button">
                    {processing ? 'Processing Single PO...' : 'PROCESS SINGLE SUPPLIER PO'}
                </button>
            </div>
        </form>
      )}

      {/* Form for Multi-Supplier Mode */}
      {canDisplayProcessingForm && isMultiSupplierMode && !isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form multi-supplier-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
            <section className="multi-supplier-assignment card">
                <h3>Assign Original Items to Suppliers</h3>
                {(orderData?.line_items || []).length === 0 && <p>No original line items to assign.</p>}
                {(orderData?.line_items || []).map((item) => (
                    <div key={`assign-item-${item.line_item_id}`} className="item-assignment-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--spacing-sm)'}}>
                        <span style={{ flexBasis: '60%' }}>({item.quantity}) {item.original_sku || 'N/A'}</span>
                        <select value={lineItemAssignments[item.line_item_id] || ''} onChange={(e) => handleLineItemSupplierAssignment(item.line_item_id, e.target.value)} disabled={disableAllActions || suppliers.length === 0} style={{flexBasis: '35%'}}>
                            <option value="">-- Assign Supplier --</option>
                            {(suppliers || []).map(supplier => (<option key={supplier.id} value={supplier.id}>{supplier.name}</option>))}
                        </select>
                    </div>
                ))}
            </section>
            {[...new Set(Object.values(lineItemAssignments))].filter(id => id).map(supplierId => {
                const supplier = suppliers.find(s => s.id === parseInt(supplierId, 10));
                if (!supplier) return null;
                const itemsForThisSupplier = (orderData?.line_items || []).filter(item => lineItemAssignments[item.line_item_id] === supplierId);
                const currentPoShipDetails = multiSupplierShipmentDetails[supplierId] || {};
                const selectedPoShipOption = getSelectedShippingOption(currentPoShipDetails.method);

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
                        <div className="form-grid shipment-details-multi card-inset" style={{border: '1px solid var(--border-medium)', padding: 'var(--spacing-md)', borderRadius: '4px', marginTop: 'var(--spacing-md)'}}>
                            <h5 style={{gridColumn: '1 / -1', marginBottom: 'var(--spacing-sm)'}}>Shipment Details for this PO (Optional - for Label Generation)</h5>
                            <div className="form-group" style={{gridColumn: '1 / -1'}}>
                                <label htmlFor={`shipMethod-multi-${supplierId}`}>Method:</label>
                                <select
                                    id={`shipMethod-multi-${supplierId}`}
                                    value={currentPoShipDetails.method || ''}
                                    onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'method', e.target.value)}
                                    disabled={disableAllActions}
                                    style={{width: '100%'}}
                                >
                                    <option value="">-- No Label / Method --</option>
                                    {SHIPPING_METHODS_OPTIONS.map((opt, index) => <option key={`${opt.value}-${opt.carrier}-multi-${supplierId}-${index}`} value={opt.value}>{opt.label}</option>)}
                                </select>
                            </div>
                             <div className="form-group" style={{gridColumn: '1 / -1'}}>
                                <label htmlFor={`shipWeight-multi-${supplierId}`}>Weight (lbs):</label>
                                <input
                                    id={`shipWeight-multi-${supplierId}`}
                                    type="number"
                                    className="weight-input-field"
                                    value={currentPoShipDetails.weight || ''}
                                    onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'weight', e.target.value)}
                                    step="0.1"
                                    min="0.1"
                                    placeholder="e.g., 5.0"
                                    disabled={disableAllActions || !currentPoShipDetails.method}
                                    style={{width: '100%'}}
                                />
                            </div>
                            {selectedPoShipOption?.carrier === 'fedex' && (
                                <>
                                    <div className="form-group" style={{gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)'}}>
                                        <input
                                            type="checkbox"
                                            id={`billToCustomerFedexMulti-${supplierId}`}
                                            checked={currentPoShipDetails.billToCustomerFedexAccount || false}
                                            onChange={(e) => {
                                                handleMultiSupplierShipmentDetailChange(supplierId, 'billToCustomerFedexAccount', e.target.checked);
                                                if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', orderData.order.customer_fedex_account_number);
                                                } else if (!e.target.checked) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', '');
                                                }
                                            }}
                                            disabled={disableAllActions}
                                        />
                                        <label htmlFor={`billToCustomerFedexMulti-${supplierId}`} style={{fontWeight: 'normal', marginBottom: 0}}>Bill Customer FedEx:</label>
                                    </div>
                                    {currentPoShipDetails.billToCustomerFedexAccount && (
                                        <div className="form-group" style={{gridColumn: '1 / -1'}}>
                                            <label htmlFor={`customerFedexAccountMulti-${supplierId}`}>Cust. FedEx Acct #:</label>
                                            <input
                                                type="text"
                                                id={`customerFedexAccountMulti-${supplierId}`}
                                                value={currentPoShipDetails.customerFedexAccount || ''}
                                                onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'customerFedexAccount', e.target.value)}
                                                placeholder="FedEx Account"
                                                required
                                                disabled={disableAllActions}
                                                style={{width: '100%'}}
                                            />
                                        </div>
                                    )}
                                </>
                            )}
                            {selectedPoShipOption?.carrier === 'ups' && (
                                <>
                                    <div className="form-group" style={{gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: 'var(--spacing-sm)'}}>
                                        <input
                                            type="checkbox"
                                            id={`billToCustomerUpsMulti-${supplierId}`}
                                            checked={currentPoShipDetails.billToCustomerUpsAccount || false}
                                            onChange={(e) => {
                                                handleMultiSupplierShipmentDetailChange(supplierId, 'billToCustomerUpsAccount', e.target.checked);
                                                if (e.target.checked && orderData?.order?.is_bill_to_customer_account && orderData?.order?.customer_ups_account_number) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerUpsAccount', orderData.order.customer_ups_account_number);
                                                } else if (!e.target.checked) {
                                                    handleMultiSupplierShipmentDetailChange(supplierId, 'customerUpsAccount', '');
                                                }
                                            }}
                                            disabled={disableAllActions}
                                        />
                                        <label htmlFor={`billToCustomerUpsMulti-${supplierId}`} style={{fontWeight: 'normal', marginBottom: 0}}>Bill Customer UPS:</label>
                                    </div>
                                    {currentPoShipDetails.billToCustomerUpsAccount && (
                                        <div className="form-group" style={{gridColumn: '1 / -1'}}>
                                            <label htmlFor={`customerUpsAccountMulti-${supplierId}`}>Cust. UPS Acct #:</label>
                                            <input
                                                type="text"
                                                id={`customerUpsAccountMulti-${supplierId}`}
                                                value={currentPoShipDetails.customerUpsAccount || ''}
                                                onChange={(e) => handleMultiSupplierShipmentDetailChange(supplierId, 'customerUpsAccount', e.target.value)}
                                                placeholder="UPS Account"
                                                required
                                                disabled={disableAllActions}
                                                style={{width: '100%'}}
                                            />
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                        <div className="form-grid" style={{marginTop: 'var(--spacing-md)'}}>
                            <label htmlFor={`poNotes-${supplierId}`} style={{gridColumn: '1 / -1', textAlign: 'left'}}>PO Notes for {supplier.name}:</label>
                            <textarea id={`poNotes-${supplierId}`} value={poNotesBySupplier[supplierId] || ''} onChange={(e) => handlePoNotesBySupplierChange(supplierId, e.target.value)} rows="3" disabled={disableAllActions} style={{gridColumn: '1 / -1', width: '100%'}}/>
                        </div>
                    </section>
                );
            })}
            <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
                 <h3>Packing Slip Branding</h3>
                 <div className="form-grid">
                    <label htmlFor="brandingOptionMultiGlobal">Branding:</label>
                    <select
                        id="brandingOptionMultiGlobal"
                        value={isBlindDropShip ? 'blind' : 'g1'}
                        onChange={handleBrandingChange}
                        disabled={disableEditableFormFields}
                    >
                        <option value="g1">Global One Technology Branding</option>
                        <option value="blind">Blind Ship (Generic Packing Slip)</option>
                    </select>
                </div>
            </section>
            
            <ProfitDisplay info={profitInfo} />
            
            <div className="order-actions">
                 <button type="submit" disabled={disableAllActions || processing || [...new Set(Object.values(lineItemAssignments))].filter(id => id).length === 0} className="process-order-button">
                    {processing ? 'Processing Multiple POs...' : 'PROCESS ALL ASSIGNED POs'}
                </button>
            </div>
        </form>
      )}

      {/* Form for G1 Onsite Fulfillment */}
      {canDisplayProcessingForm && isG1OnsiteFulfillmentMode && (
        <form onSubmit={handleProcessOrder} className={`processing-form g1-onsite-fulfillment-active ${disableEditableFormFields ? 'form-disabled' : ''}`}>
          <section className="shipment-info card">
            <h3>Shipment Information</h3>
            <div className="form-grid">
              <label htmlFor="shipmentMethodG1">Method:</label>
              <select
                id="shipmentMethodG1"
                value={shipmentMethod}
                onChange={handleShipmentMethodChange}
                disabled={disableEditableFormFields}
                required={(orderData?.line_items || []).length > 0}
              >
                  {SHIPPING_METHODS_OPTIONS.map((opt, index) => <option key={`${opt.value}-${opt.carrier}-g1-${index}`} value={opt.value}>{opt.label}</option>)}
              </select>

              <label htmlFor="shipmentWeightG1">Weight (lbs):</label>
              <input
                  type="number"
                  id="shipmentWeightG1"
                  className="weight-input-field"
                  value={shipmentWeight}
                  onChange={handleShipmentWeightChange}
                  step="0.1"
                  min="0.1"
                  placeholder="e.g., 5.0"
                  required={(orderData?.line_items || []).length > 0}
                  disabled={disableEditableFormFields}
              />

              <label htmlFor="brandingOptionG1">Branding:</label>
                <select
                    id="brandingOptionG1"
                    value={isBlindDropShip ? 'blind' : 'g1'}
                    onChange={handleBrandingChange}
                    disabled={disableEditableFormFields}
                >
                    <option value="g1">Global One Technology Branding</option>
                    <option value="blind">Blind Ship (Generic Packing Slip)</option>
                </select>

              {currentSelectedShippingOption?.carrier === 'fedex' && (orderData?.line_items || []).length > 0 && (
                <>
                    <label htmlFor="billToCustomerFedexG1">Bill Customer FedEx:</label>
                    <input
                        type="checkbox"
                        id="billToCustomerFedexG1"
                        checked={billToCustomerFedex}
                        onChange={(e) => {
                            setBillToCustomerFedex(e.target.checked);
                             if (e.target.checked && orderData?.order?.is_bill_to_customer_fedex_account && orderData?.order?.customer_fedex_account_number) {
                                setCustomerFedexAccountNumber(orderData.order.customer_fedex_account_number);
                            } else if (!e.target.checked) {
                                setCustomerFedexAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                    />
                    {billToCustomerFedex && (
                    <>
                        <label htmlFor="customerFedexAccountG1">Customer FedEx Acct #:</label>
                        <input
                            type="text"
                            id="customerFedexAccountG1"
                            value={customerFedexAccountNumber}
                            onChange={(e) => setCustomerFedexAccountNumber(e.target.value)}
                            placeholder="FedEx Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                    </>
                    )}
                </>
               )}
               {currentSelectedShippingOption?.carrier === 'ups' && (orderData?.line_items || []).length > 0 && (
                <>
                    <label htmlFor="billToCustomerUpsG1">Bill Customer UPS:</label>
                    <input
                        type="checkbox"
                        id="billToCustomerUpsG1"
                        checked={billToCustomerUps}
                        onChange={(e) => {
                            setBillToCustomerUps(e.target.checked);
                             if (e.target.checked && orderData?.order?.is_bill_to_customer_account && orderData?.order?.customer_ups_account_number) {
                                setCustomerUpsAccountNumber(orderData.order.customer_ups_account_number);
                            } else if (!e.target.checked) {
                                setCustomerUpsAccountNumber('');
                            }
                        }}
                        disabled={disableEditableFormFields}
                    />
                    {billToCustomerUps && (
                    <>
                        <label htmlFor="customerUpsAccountG1">Customer UPS Acct #:</label>
                        <input
                            type="text"
                            id="customerUpsAccountG1"
                            value={customerUpsAccountNumber}
                            onChange={(e) => setCustomerUpsAccountNumber(e.target.value)}
                            placeholder="UPS Account Number"
                            required
                            disabled={disableEditableFormFields}
                        />
                    </>
                    )}
                </>
               )}
            </div>
            </section>
            
            {/* ProfitDisplay is intentionally REMOVED from G1 Onsite Fulfillment active processing form */}
            
            <div className="order-actions">
                <button type="submit" disabled={disableAllActions || processing} className="process-order-button">
                    {processing ? 'Processing G1 Fulfillment...' : 'PROCESS G1 ONSITE FULFILLMENT'}
                </button>
            </div>
        </form>
      )}

      <div className="manual-actions-section" style={{marginTop: "20px"}}>
           {order && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') && !isActuallyProcessed && (
              <button onClick={() => handleManualStatusUpdate('Completed Offline')} className="manual-action-button button-mark-completed" disabled={disableAllActions}>
                  {manualStatusUpdateInProgress && (order.status?.toLowerCase() === 'international_manual' || order.status?.toLowerCase() === 'pending') ? 'Updating...' : 'Mark as Completed Offline'}
              </button>
          )}
           {order && order.status?.toLowerCase() === 'new' && !isActuallyProcessed && (
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
          {(isActuallyProcessed || processSuccess) && (
              <button type="button" onClick={() => navigate('/')} className="back-to-dashboard-button" disabled={processing && !processSuccess}>
                  BACK TO DASHBOARD
              </button>
          )}
          {isActuallyProcessed && !processSuccess && (
              <div style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
                  This order has been {order.status?.toLowerCase()} and no further automated actions are available.
              </div>
          )}
      </div>
    </div>
  );
}

export default OrderDetail;