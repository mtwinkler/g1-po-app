// src/components/InternationalOrderProcessor.jsx
import React, { useState, useEffect } from 'react';

const MULTI_SUPPLIER_MODE_VALUE = "_MULTI_SUPPLIER_MODE_";
const G1_ONSITE_INTERNATIONAL_VALUE = "_G1_ONSITE_INTL_";

const SHIPPING_METHODS_OPTIONS_INTL = [
    { value: "07", label: "UPS Worldwide Express", carrier: "ups" },
    { value: "08", label: "UPS Worldwide Expedited", carrier: "ups" },
    { value: "54", label: "UPS Worldwide Express Plus", carrier: "ups" },
    { value: "65", label: "UPS Worldwide Saver", carrier: "ups" },
    { value: "11", label: "UPS Standard", carrier: "ups" },
];

const mapBcShippingToIntlServiceCode = (bcShippingMethod) => {
    if (!bcShippingMethod || typeof bcShippingMethod !== 'string') {
        return null;
    }
    const methodNormalized = bcShippingMethod.toLowerCase().replace(/[^a-z0-9\s]/gi, '').replace(/\s+/g, ' ');

    if (methodNormalized.includes("ups worldwide express plus")) return "54";
    if (methodNormalized.includes("ups worldwide express")) return "07";
    if (methodNormalized.includes("ups worldwide expedited")) return "08";
    if (methodNormalized.includes("ups worldwide saver")) return "65";
    if (methodNormalized.includes("ups standard")) return "11";

    if (methodNormalized.includes("worldwide express plus")) return "54";
    if (methodNormalized.includes("worldwide express")) return "07";
    if (methodNormalized.includes("worldwide expedited")) return "08";
    if (methodNormalized.includes("worldwide saver")) return "65";
    if (methodNormalized.includes("standard")) return "11";

    console.warn(`InternationalOrderProcessor: Could not map BigCommerce shipping method "${bcShippingMethod}" (normalized: "${methodNormalized}") to a known UPS international service code.`);
    return null;
};

const ProfitDisplay = ({ info }) => {
    if (!info || !info.isCalculable) { return null; }
    const formatCurrency = (value) => {
        const numValue = Number(value);
        if (isNaN(numValue)) return 'N/A';
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(numValue);
    };
    const profitAmount = Number(info.profitAmount);
    const isProfitable = !isNaN(profitAmount) && profitAmount >= 0;
    const cardStyle = { backgroundColor: isProfitable ? 'rgba(40, 167, 69, 0.6)' : 'rgba(220, 53, 69, 0.6)' };
    const profitAmountColor = isProfitable ? 'var(--success-text)' : 'var(--error-text)';
    return (
        <div className="profit-display-card card" style={cardStyle}>
            <h3>Profitability Analysis</h3>
            <div className="profit-grid">
                <span>Revenue:</span><span>{formatCurrency(info.totalRevenue)}</span>
                <span>Cost:</span><span>{formatCurrency(info.totalCost)}</span>
                <hr style={{ gridColumn: '1 / -1', border: 'none', borderTop: '1px solid #ccc', margin: '12px 0' }} />
                <div style={{ textAlign: 'center' }}><div style={{ fontWeight: 'bold' }}>Profit:</div><div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>{formatCurrency(info.profitAmount)}</div></div>
                <div style={{ textAlign: 'center' }}><div style={{ fontWeight: 'bold' }}>Margin:</div><div style={{ fontWeight: 'bold', color: profitAmountColor, fontSize: '2em' }}>{isNaN(Number(info.profitMargin)) ? 'N/A' : Number(info.profitMargin).toFixed(2)}%</div></div>
            </div>
        </div>
    );
};

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => { setDebouncedValue(value); }, delay);
    return () => { clearTimeout(handler); };
  }, [value, delay]);
  return debouncedValue;
}

function escapeRegExp(string) {
  if (typeof string !== 'string') return '';
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}


function InternationalOrderProcessor({
    orderData,
    suppliers,
    apiService,
    setProcessError,
    onSuccessRefresh
}) {
  const { order, line_items: originalLineItemsFromData, billing_address } = orderData;
  const orderId = order.id;
  const cleanPullSuffix = " - clean pull";
  const originalLineItems = originalLineItemsFromData || [];

  const [internationalApiDetails, setInternationalApiDetails] = useState(null);
  const [loadingApiDetails, setLoadingApiDetails] = useState(true);
  const [apiDetailsError, setApiDetailsError] = useState(null);
  const [dynamicComplianceValues, setDynamicComplianceValues] = useState({});
  const [exemptions, setExemptions] = useState({});

  const [selectedFulfillmentStrategy, setSelectedFulfillmentStrategy] = useState('');
  const [purchaseItems, setPurchaseItems] = useState([]);
  const [singleOrderPoNotes, setSingleOrderPoNotes] = useState('');
  const [isBlindDropShip, setIsBlindDropShip] = useState(false);
  const [skuToLookup, setSkuToLookup] = useState({ index: -1, sku: '' });
  const debouncedSku = useDebounce(skuToLookup.sku, 500);

  const [profitInfo, setProfitInfo] = useState({ isCalculable: false });

  const [shipmentWeight, setShipmentWeight] = useState('1');
  const [packageLength, setPackageLength] = useState('');
  const [packageWidth, setPackageWidth] = useState('');
  const [packageHeight, setPackageHeight] = useState('');
  const [selectedShippingService, setSelectedShippingService] = useState('');
  const [descriptionOfGoods, setDescriptionOfGoods] = useState('');
  const [paymentType, setPaymentType] = useState('01');

  const [billToCustomerUps, setBillToCustomerUps] = useState(false);
  const [customerUpsAccountNumber, setCustomerUpsAccountNumber] = useState('');
  const [customerUpsAccountZipCode, setCustomerUpsAccountZipCode] = useState('');

  const [isProcessingOrder, setIsProcessingOrder] = useState(false);
  const [processSuccess, setProcessSuccess] = useState(false);
  const [newShipmentInfo, setNewShipmentInfo] = useState({
      poNumber: null, trackingNumber: null, labelUrl: null,
      poPdfUrl: null, packingSlipPdfUrl: null
  });

  useEffect(() => {
    const fetchInternationalDetailsFromApi = async () => {
      if (order?.id && apiService) {
        setLoadingApiDetails(true);
        setApiDetailsError(null);
        try {
          const details = await apiService.get(`/order/${order.id}/international-details`);
          setInternationalApiDetails(details); // Set details first

          // Initialize compliance and exemptions based on 'details'
          const initialValues = {};
          const initialExemptions = {};
          if (details?.required_compliance_fields) {
            details.required_compliance_fields.forEach(field => {
              const fieldKey = field.field_label;
              if (field.id_owner === 'Shipper' && details.shipper_ein) {
                initialValues[fieldKey] = details.shipper_ein;
              } else if (order.compliance_info?.[fieldKey] !== undefined) {
                initialValues[fieldKey] = order.compliance_info[fieldKey];
              } else {
                initialValues[fieldKey] = '';
              }
              if (field.has_exempt_option) {
                initialExemptions[fieldKey] = (order.compliance_info?.[fieldKey] === 'EXEMPT');
              }
            });
          }
          setDynamicComplianceValues(initialValues);
          setExemptions(initialExemptions);

          // --- Logic for Overall Shipment Description (depends on 'details' and 'originalLineItems') ---
          let determinedShipmentDesc = "Computer Components"; // Default generic term
          const commonSuffix = " for computers";
          const characterLimit = 50;

          if (details?.line_items_customs_info && details.line_items_customs_info.length > 0) {
              const customsDescriptions = details.line_items_customs_info
                  .map(item => item.customs_description && item.customs_description.trim())
                  .filter(Boolean);

              const uniqueDescriptions = [...new Set(customsDescriptions)];

              if (uniqueDescriptions.length === 1) {
                  determinedShipmentDesc = uniqueDescriptions[0];
              } else if (uniqueDescriptions.length > 1) {
                  const strippedDescriptions = uniqueDescriptions.map(desc => {
                      if (desc.toLowerCase().endsWith(commonSuffix.toLowerCase())) {
                          return desc.substring(0, desc.length - commonSuffix.length).trim();
                      }
                      return desc;
                  });

                  let joinedStripped = strippedDescriptions.join(', ');
                  
                  if ((joinedStripped + commonSuffix).length <= characterLimit) {
                      determinedShipmentDesc = joinedStripped + commonSuffix;
                  } else if (joinedStripped.length <= characterLimit) {
                      determinedShipmentDesc = joinedStripped;
                  } else {
                      let currentDesc = "";
                      for (let i = 0; i < strippedDescriptions.length; i++) {
                          const nextDescPart = strippedDescriptions[i];
                          const separator = currentDesc ? ", " : "";
                          if ((currentDesc + separator + nextDescPart).length <= characterLimit) {
                              currentDesc += separator + nextDescPart;
                          } else {
                              if (i === 0 && nextDescPart.length > characterLimit) { // First item itself is too long
                                  currentDesc = nextDescPart.substring(0, characterLimit - 3) + "...";
                              }
                              break; 
                          }
                      }
                      if (currentDesc) {
                          determinedShipmentDesc = currentDesc;
                      } else if (strippedDescriptions[0]) { 
                           determinedShipmentDesc = strippedDescriptions[0].substring(0, characterLimit -3) + "...";
                      }
                      // If determinedShipmentDesc is still "Computer Components", it means the smart joining didn't produce a better result or items were too long.
                  }
              } else if (originalLineItems && originalLineItems.length > 0 && (originalLineItems[0].line_item_name || originalLineItems[0].name)) {
                  determinedShipmentDesc = originalLineItems[0].line_item_name || originalLineItems[0].name;
              }
          } else if (originalLineItems && originalLineItems.length > 0 && (originalLineItems[0].line_item_name || originalLineItems[0].name)) {
              determinedShipmentDesc = originalLineItems[0].line_item_name || originalLineItems[0].name;
          }
          
          setDescriptionOfGoods(String(determinedShipmentDesc || 'Assorted Goods').substring(0, characterLimit));
          // --- End of Logic for Overall Shipment Description ---

        } catch (err) {
          const errorMsg = err.data?.message || err.message || "Failed to load detailed international order data.";
          setApiDetailsError(errorMsg);
          if (setProcessError) setProcessError(errorMsg);
        } finally {
          setLoadingApiDetails(false);
        }
      }
    };

    if (order) {
        fetchInternationalDetailsFromApi(); // This will set internationalApiDetails, then the effect below will run
        setBillToCustomerUps(order.is_bill_to_customer_account || false);
        setCustomerUpsAccountNumber(order.customer_ups_account_number || '');
        const billingZip = billing_address?.zip || order.customer_billing_zip;
        setCustomerUpsAccountZipCode(billingZip ? String(billingZip).replace(/\s+/g, '') : '');

        let methodStringToMap = order.customer_shipping_method;
        if (order.is_bill_to_customer_account && order.customer_selected_freight_service) {
            methodStringToMap = order.customer_selected_freight_service;
        }
        console.log("InternationalOrderProcessor: Attempting to map shipping string:", methodStringToMap);
        const mappedServiceCode = mapBcShippingToIntlServiceCode(methodStringToMap);
        console.log("InternationalOrderProcessor: Mapped service code:", mappedServiceCode);
        if (mappedServiceCode) {
            setSelectedShippingService(mappedServiceCode);
        } else if (SHIPPING_METHODS_OPTIONS_INTL.length > 0) {
            setSelectedShippingService(SHIPPING_METHODS_OPTIONS_INTL[0].value);
            if (methodStringToMap) {
                 console.warn(`InternationalOrderProcessor: Could not map shipping method "${methodStringToMap}" to a service code. Defaulting to ${SHIPPING_METHODS_OPTIONS_INTL[0].label}.`);
            }
        } else {
            setSelectedShippingService('');
        }
    }
  }, [order?.id, apiService, order?.compliance_info, setProcessError, originalLineItems, order, billing_address?.zip]);
  // Note: internationalApiDetails is removed from this specific useEffect's dependency array to avoid re-running complex logic on its every change.
  // The description logic is now inside the async function that fetches 'details'.

  useEffect(() => {
    const isSupplierSelectedForPO = selectedFulfillmentStrategy &&
                                    selectedFulfillmentStrategy !== "" &&
                                    selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE &&
                                    !isNaN(parseInt(selectedFulfillmentStrategy, 10));

    if (isSupplierSelectedForPO) {
        const supplierId = parseInt(selectedFulfillmentStrategy, 10);
        const supplier = suppliers.find(s => s.id === supplierId);
        setSingleOrderPoNotes(supplier?.defaultponotes || '');
        const initialItemsForPoForm = originalLineItems.map(item => ({
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
        setPurchaseItems(initialItemsForPoForm);
    } else {
        setPurchaseItems([]);
        setSingleOrderPoNotes('');
    }
  }, [originalLineItems, selectedFulfillmentStrategy, suppliers, cleanPullSuffix]);

  useEffect(() => {
    if (!apiService || !debouncedSku || skuToLookup.index === -1) return;
    const isSupplierSelectedForPO = selectedFulfillmentStrategy &&
                                    selectedFulfillmentStrategy !== "" &&
                                    selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE &&
                                    !isNaN(parseInt(selectedFulfillmentStrategy, 10));
    if (!isSupplierSelectedForPO) return;

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
                    newDescription = (existingDesc ? `${existingDesc} ` : "") + cleanPullSuffix.trim();
                    if (newDescription.startsWith(` ${cleanPullSuffix.trim()}`)) newDescription = cleanPullSuffix.trim();
                }
                updatedItems[skuToLookup.index] = { ...updatedItems[skuToLookup.index], description: newDescription };
            }
            return updatedItems;
        });
      } catch (error) {
          if (error.name !== 'AbortError' && error.status !== 401 && error.status !== 403) {
            console.error("Error fetching SKU description:", error);
          }
      }
    };
    fetchDescription();
    return () => abortController.abort();
  }, [debouncedSku, skuToLookup.index, cleanPullSuffix, apiService, selectedFulfillmentStrategy]);

  useEffect(() => {
    if (!orderData || !originalLineItems) {
        if (profitInfo.isCalculable) setProfitInfo({ isCalculable: false });
        return;
    }
    const revenue = originalLineItems.reduce((sum, item) => sum + (parseFloat(item.sale_price || 0) * parseInt(item.quantity || 0, 10)), 0);
    let cost = 0;
    let isCalculable = false;

    const isSupplierPOSelected = selectedFulfillmentStrategy &&
                                 selectedFulfillmentStrategy !== "" &&
                                 selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE &&
                                 !isNaN(parseInt(selectedFulfillmentStrategy, 10));

    if (isSupplierPOSelected) {
        if (purchaseItems.length > 0) {
            const allCostsEntered = purchaseItems.every(item => item.unit_cost !== undefined && item.unit_cost !== '' && !isNaN(parseFloat(item.unit_cost)));
            if (allCostsEntered) {
                cost = purchaseItems.reduce((total, item) => total + (parseFloat(item.unit_cost) * parseInt(item.quantity, 10)), 0);
                isCalculable = true;
            }
        } else if (originalLineItems.length === 0) {
            isCalculable = true; cost = 0;
        }
    } else if (selectedFulfillmentStrategy === G1_ONSITE_INTERNATIONAL_VALUE) {
        cost = 0;
        isCalculable = originalLineItems.length > 0 || revenue > 0;
    } else {
        isCalculable = false;
    }

    if (isCalculable) {
        const profit = revenue - cost;
        const margin = revenue > 0 ? (profit / revenue) * 100 : 0;
        setProfitInfo({ totalRevenue: revenue, totalCost: cost, profitAmount: profit, profitMargin: margin, isCalculable: true });
    } else {
        setProfitInfo({ isCalculable: false, totalRevenue: revenue, totalCost:0, profitAmount:0, profitMargin:0 });
    }
  }, [orderData, originalLineItems, purchaseItems, selectedFulfillmentStrategy, profitInfo.isCalculable]);


  const handleFulfillmentStrategyChange = (e) => {
    const value = e.target.value;
    setSelectedFulfillmentStrategy(value);
    if(setProcessError) setProcessError(null);
    setProcessSuccess(false);
    setApiDetailsError(null);
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

  const handleDynamicComplianceChange = (fieldName, value) => {
    setDynamicComplianceValues(prev => ({ ...prev, [fieldName]: value }));
  };

  const handleExemptionChange = (fieldName, isChecked) => {
    setExemptions(prev => ({ ...prev, [fieldName]: isChecked }));
    if (isChecked) {
        handleDynamicComplianceChange(fieldName, 'EXEMPT');
    } else {
        const originalCheckoutValue = order.compliance_info?.[fieldName];
        handleDynamicComplianceChange(fieldName, originalCheckoutValue || '');
    }
  };

  const handleBrandingChange = (event) => {
    setIsBlindDropShip(event.target.value === 'blind');
  };

  const handleProcessCombinedOrder = async () => {
    if(setProcessError) setProcessError(null);
    setIsProcessingOrder(true);
    setProcessSuccess(false);
    setNewShipmentInfo({ poNumber: null, trackingNumber: null, labelUrl: null, poPdfUrl: null, packingSlipPdfUrl: null });

    let poDataPayload = null;

    if (!internationalApiDetails || !order || !originalLineItems) { if(setProcessError) setProcessError("International details or order data not loaded."); setIsProcessingOrder(false); return; }
    if (!shipmentWeight || parseFloat(shipmentWeight) <= 0) { if(setProcessError) setProcessError("Shipment weight must be a positive number."); setIsProcessingOrder(false); return; }
    if (!selectedShippingService) { if(setProcessError) setProcessError("Please select an international shipping service."); setIsProcessingOrder(false); return; }
    if (!descriptionOfGoods.trim()) { if(setProcessError) setProcessError("Please provide a general description of goods for the shipment."); setIsProcessingOrder(false); return; }
    const l = parseFloat(packageLength);
    const w = parseFloat(packageWidth);
    const h = parseFloat(packageHeight);
    if ((packageLength && (isNaN(l) || l <= 0)) || (packageWidth && (isNaN(w) || w <= 0)) || (packageHeight && (isNaN(h) || h <= 0))) {
        if(setProcessError) setProcessError("If dimensions are entered, they must be positive numbers."); setIsProcessingOrder(false); return;
    }
    if (billToCustomerUps && (!customerUpsAccountNumber.trim() || !customerUpsAccountZipCode.trim())) {
        if(setProcessError) setProcessError("Recipient UPS Account Number and Account Postal Code are required for Bill Recipient.");
        setIsProcessingOrder(false);
        return;
    }

    const isSupplierPOSelected = selectedFulfillmentStrategy &&
                                 selectedFulfillmentStrategy !== "" &&
                                 selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE &&
                                 !isNaN(parseInt(selectedFulfillmentStrategy, 10));

    if (isSupplierPOSelected) {
        if (purchaseItems.length === 0 && originalLineItems.length > 0) { if(setProcessError) setProcessError("No items configured for PO, but original order has items."); setIsProcessingOrder(false); return; }
        let itemValidationError = null;
        const finalPoLineItems = purchaseItems.map((item, index) => {
            const quantityInt = parseInt(item.quantity, 10);
            const costFloat = parseFloat(item.unit_cost);
            if (isNaN(quantityInt) || quantityInt <= 0) { itemValidationError = `PO Item #${index + 1}: Quantity must be > 0.`; return null; }
            if (item.unit_cost === undefined || item.unit_cost === '' || isNaN(costFloat) || costFloat < 0) { itemValidationError = `PO Item #${index + 1}: Unit cost is invalid.`; return null; }
            if (!String(item.sku).trim()) { itemValidationError = `PO Item #${index + 1}: SKU is required.`; return null; }
            if (!String(item.description).trim()) { itemValidationError = `PO Item #${index + 1}: Description is required.`; return null; }
            return {
                original_order_line_item_id: item.original_order_line_item_id,
                sku: String(item.sku).trim(),
                description: String(item.description).trim(),
                quantity: quantityInt,
                unitCost: costFloat.toFixed(2)
            };
        }).filter(Boolean);
        if (itemValidationError) { if(setProcessError) setProcessError(itemValidationError); setIsProcessingOrder(false); return; }
        if (finalPoLineItems.length === 0 && originalLineItems.length > 0) { if(setProcessError) setProcessError("No valid line items to purchase for the PO, but original order has items."); setIsProcessingOrder(false); return; }

        if (finalPoLineItems.length > 0 || (originalLineItems.length === 0 && purchaseItems.length === 0) ) {
             poDataPayload = {
                supplierId: parseInt(selectedFulfillmentStrategy, 10),
                poNotes: singleOrderPoNotes,
                lineItems: finalPoLineItems,
                is_blind_drop_ship: isBlindDropShip
            };
        } else if (originalLineItems.length > 0 && finalPoLineItems.length === 0) { if(setProcessError) setProcessError("Cannot create an empty PO when original order has items."); setIsProcessingOrder(false); return; }
    }

    const shipperDetails = {
        Name: "Global One Technology", AttentionName: "Order Fulfillment",
        TaxIdentificationNumber: internationalApiDetails.shipper_ein, // Ensure internationalApiDetails is loaded
        Phone: { Number: "8774183246" },
        Address: { AddressLine: ["4916 S 184th Plaza"], City: "Omaha", StateProvinceCode: "NE", PostalCode: "68135", CountryCode: "US" },
        ShipperNumber: "EW1847"
    };

    let paymentInformationPayload;
    if (billToCustomerUps && customerUpsAccountNumber.trim() && customerUpsAccountZipCode.trim() && order?.customer_shipping_country_iso2) {
       console.log(`DEBUG INTL_PROCESSOR: Constructing BillReceiver with Customer UPS Account: ${customerUpsAccountNumber}, Account Postal: ${customerUpsAccountZipCode}, Account Country: ${order.customer_shipping_country_iso2}`);
       paymentInformationPayload = {
           ShipmentCharge: { Type: paymentType, BillReceiver: { AccountNumber: customerUpsAccountNumber.trim(), Address: { PostalCode: customerUpsAccountZipCode.trim().replace(/\s+/g, ''), CountryCode: order.customer_shipping_country_iso2.toUpperCase() }}}
       };
   } else {
       console.log("DEBUG INTL_PROCESSOR: Billing to Sender UPS (G1 Technology)");
       paymentInformationPayload = {
           ShipmentCharge: { Type: paymentType, BillShipper: { AccountNumber: "EW1847" } }
       };
   }

    let shipToName = order.customer_company || `${order.customer_shipping_first_name || ''} ${order.customer_shipping_last_name || ''}`.trim() || "Receiver";
    shipToName = shipToName.substring(0,35);
    let shipToAttentionName = `${order.customer_shipping_first_name || ''} ${order.customer_shipping_last_name || ''}`.trim() || order.customer_name || shipToName || "Receiving Dept";
    shipToAttentionName = shipToAttentionName.substring(0,35);
    if (!shipToAttentionName) shipToAttentionName = shipToName;

    const finalComplianceValues = {...dynamicComplianceValues};
    Object.keys(exemptions).forEach(key => { if (exemptions[key]) finalComplianceValues[key] = 'EXEMPT'; });
    const receiverTaxField = internationalApiDetails?.required_compliance_fields?.find(f => f.id_owner === 'Receiver' && finalComplianceValues[f.field_label] && finalComplianceValues[f.field_label] !== 'EXEMPT');
    const shipToTaxId = receiverTaxField ? finalComplianceValues[receiverTaxField.field_label] : '';

    let totalInvoiceMonetaryValue = 0;
    if (originalLineItems && originalLineItems.length > 0) {
        totalInvoiceMonetaryValue = originalLineItems.reduce((sum, item) => {
            const price = parseFloat(item.sale_price || 0);
            const quantity = parseInt(item.quantity || 0, 10);
            return sum + (price * quantity);
        }, 0);
    }
    totalInvoiceMonetaryValue = parseFloat(totalInvoiceMonetaryValue.toFixed(2));

    let invoiceLineTotalObject = null;
    if (totalInvoiceMonetaryValue >= 1.00) {
        invoiceLineTotalObject = { CurrencyCode: "USD", MonetaryValue: totalInvoiceMonetaryValue.toFixed(2) };
    }

    const shipmentObject = {
        Description: descriptionOfGoods, // Already truncated in state
        Shipper: shipperDetails,
        ShipTo: {
            Name: shipToName, AttentionName: shipToAttentionName, TaxIdentificationNumber: shipToTaxId,
            Phone: { Number: order.customer_phone ? String(order.customer_phone).replace(/\D/g, '') : undefined },
            Address: {
              AddressLine: [order.customer_shipping_address_line1, order.customer_shipping_address_line2].filter(Boolean),
              City: order.customer_shipping_city, PostalCode: order.customer_shipping_zip, CountryCode: order.customer_shipping_country_iso2,
              ...( (order.customer_shipping_country_iso2?.toUpperCase() === 'US' || order.customer_shipping_country_iso2?.toUpperCase() === 'CA') && order.customer_shipping_state && { StateProvinceCode: order.customer_shipping_state })
            }
        },
        PaymentInformation: paymentInformationPayload,
        Service: { Code: selectedShippingService },
        Package: {
            Description: "Assorted Goods", Packaging: { Code: "02" },
            PackageWeight: { UnitOfMeasurement: { Code: "LBS" }, Weight: String(shipmentWeight) },
            ...( (parseFloat(packageLength) > 0 && parseFloat(packageWidth) > 0 && parseFloat(packageHeight) > 0) && 
               { Dimensions: { UnitOfMeasurement: { Code: "IN" }, Length: String(packageLength), Width: String(packageWidth), Height: String(packageHeight) } })
        },
        ShipmentServiceOptions: {
            InternationalForms: {
              FormType: "01", CurrencyCode: "USD",
              Product: internationalApiDetails?.line_items_customs_info?.map(item => {
                const originalItemDetail = originalLineItems.find(oli => oli.line_item_id === item.original_order_line_item_id);
                return {
                  Description: item.customs_description ? item.customs_description.substring(0, 35) : 'N/A',
                  CommodityCode: item.harmonized_tariff_code, OriginCountryCode: item.default_country_of_origin,
                  Unit: { Number: String(item.quantity), Value: String(parseFloat(originalItemDetail?.sale_price || '0.00').toFixed(2)), CurrencyCode: "USD", UnitOfMeasurement: { Code: "PCS" } },
                };
              }) || [],
              InvoiceDate: new Date().toISOString().split('T')[0].replace(/-/g, ''),
              InvoiceNumber: String(order.bigcommerce_order_id || order.id), ReasonForExport: "SALE",
              Contacts: { SoldTo: {} }
            }
        }
    };

    const destinationCountryUpper = order?.customer_shipping_country_iso2?.toUpperCase();
    if (invoiceLineTotalObject) {
        if (destinationCountryUpper === 'CA' || destinationCountryUpper === 'PR') {
            shipmentObject.InvoiceLineTotal = invoiceLineTotalObject;
        } else {
            if (shipmentObject.ShipmentServiceOptions && shipmentObject.ShipmentServiceOptions.InternationalForms) {
                shipmentObject.ShipmentServiceOptions.InternationalForms.InvoiceLineTotal = invoiceLineTotalObject;
            }
        }
    } else if (destinationCountryUpper === 'CA' || destinationCountryUpper === 'PR') {
        console.error(`ERROR INTL_PROCESSOR: InvoiceLineTotal is required for ${destinationCountryUpper} but value was < 1.00.`);
    }

    const shipmentRequestPayload = {
      ShipmentRequest: {
        Request: { RequestOption: "nonvalidate", TransactionReference: { CustomerContext: `Order-${order.bigcommerce_order_id || order.id}` } },
        Shipment: shipmentObject,
        LabelSpecification: { LabelImageFormat: { Code: "GIF" } }
      }
    };
    
    const currentBillingAddress = billing_address || {};
    let finalSoldToName = currentBillingAddress.company || (`${currentBillingAddress.first_name || ''} ${currentBillingAddress.last_name || ''}`).trim() || order.customer_name || order.customer_company || "Customer";
    let finalSoldToAttentionName = order.customer_name || finalSoldToName || "Customer Contact";
    finalSoldToName = finalSoldToName.substring(0, 35);
    finalSoldToAttentionName = finalSoldToAttentionName.substring(0, 35);
    const soldToPhone = (currentBillingAddress.phone ? String(currentBillingAddress.phone).replace(/\D/g, '') : '') || (order.customer_phone ? String(order.customer_phone).replace(/\D/g, '') : undefined);

    shipmentRequestPayload.ShipmentRequest.Shipment.ShipmentServiceOptions.InternationalForms.Contacts.SoldTo = {
        Name: finalSoldToName, AttentionName: finalSoldToAttentionName, Phone: { Number: soldToPhone },
        Address: {
            AddressLine: [currentBillingAddress.street_1, currentBillingAddress.street_2].filter(Boolean).length > 0 ? [currentBillingAddress.street_1, currentBillingAddress.street_2].filter(Boolean) : shipmentObject.ShipTo.Address.AddressLine,
            City: currentBillingAddress.city || shipmentObject.ShipTo.Address.City,
            ...( ( (currentBillingAddress.country_iso2 || order.customer_shipping_country_iso2)?.toUpperCase() === 'US' || (currentBillingAddress.country_iso2 || order.customer_shipping_country_iso2)?.toUpperCase() === 'CA') && (currentBillingAddress.state || order.customer_shipping_state) && { StateProvinceCode: currentBillingAddress.state || order.customer_shipping_state }),
            PostalCode: currentBillingAddress.zip || shipmentObject.ShipTo.Address.PostalCode,
            CountryCode: currentBillingAddress.country_iso2 || shipmentObject.ShipTo.Address.CountryCode,
        }
    };

    const finalShipmentDataPayload = { ...shipmentRequestPayload, is_blind_drop_ship: isBlindDropShip };
    const finalCombinedPayload = { po_data: poDataPayload, shipment_data: finalShipmentDataPayload };

    try {
        console.log("SENDING COMBINED PAYLOAD TO BACKEND:", JSON.stringify(finalCombinedPayload, null, 2));
        const result = await apiService.post(`/order/${order.id}/process-international-dropship`, finalCombinedPayload);
        setNewShipmentInfo({ poNumber: result.poNumber, trackingNumber: result.trackingNumber, labelUrl: result.labelUrl, poPdfUrl: result.poPdfUrl, packingSlipPdfUrl: result.packingSlipPdfUrl });
        setProcessSuccess(true);
        if (onSuccessRefresh) onSuccessRefresh();
    } catch (err) {
        const errorMsg = err.data?.message || err.message || "Failed to process international order.";
        if(setProcessError) setProcessError(errorMsg);
        setProcessSuccess(false);
    }
    finally { setIsProcessingOrder(false); }
  };
  
  if (!order) return <p className="loading-message">Loading order data...</p>;
  if (loadingApiDetails && !internationalApiDetails) return <p className="loading-message">Loading international shipping details...</p>;
  if (apiDetailsError && !loadingApiDetails) {
    return <div className="error-message card" style={{margin: '20px', padding: '20px'}}>Error loading international details: {apiDetailsError}</div>;
  }

  const disableFormFields = isProcessingOrder || processSuccess;
  const isSupplierPOFlow = selectedFulfillmentStrategy &&
                           selectedFulfillmentStrategy !== "" &&
                           selectedFulfillmentStrategy !== G1_ONSITE_INTERNATIONAL_VALUE &&
                           !isNaN(parseInt(selectedFulfillmentStrategy, 10));


  return (
    <div className="international-order-processor">
      <section className="card">
        <h3>International Order Details</h3>
        <p><strong>Destination:</strong> {internationalApiDetails?.country_name || order.customer_shipping_country} ({order.customer_shipping_country_iso2 || 'N/A'})</p>
        {order.compliance_info && Object.keys(order.compliance_info).length > 0 && (
            <div className="captured-compliance-ids card-inset">
                <h4>Captured Compliance IDs (from Checkout)</h4>
                <ul>{Object.entries(order.compliance_info).map(([key, value]) => (<li key={`checkout-${key}`}><strong>{key}:</strong> {String(value)}</li>))}</ul>
            </div>
        )}
        {(!order.compliance_info || Object.keys(order.compliance_info).length === 0) && (<p style={{marginTop: 'var(--spacing-md)'}}>No specific compliance IDs were captured from checkout.</p>)}
      </section>

      {internationalApiDetails && (
        <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
            <h4>Customs & Further Compliance Data</h4>
            {internationalApiDetails.required_compliance_fields?.length > 0 && (
            <div className="form-section" style={{marginBottom: 'var(--spacing-lg)'}}>
                <h5>Required Tax/Compliance IDs for {internationalApiDetails.country_name || order.customer_shipping_country}:</h5>
                <div className="form-grid compliance-form-grid">
                {internationalApiDetails.required_compliance_fields.map(field => {
                    const fieldKey = field.field_label; const isShipperOwned = field.id_owner === 'Shipper';
                    const inputValue = isShipperOwned ? internationalApiDetails.shipper_ein : (dynamicComplianceValues[fieldKey] || '');
                    return (
                    <React.Fragment key={fieldKey}>
                        <label htmlFor={`compliance-${fieldKey.replace(/\s+/g, '-')}`}>{field.field_label}{field.is_required && !isShipperOwned ? '*' : ''}:</label>
                        <div className="compliance-input-group">
                            <input type="text" id={`compliance-${fieldKey.replace(/\s+/g, '-')}`} value={inputValue}
                                onChange={(e) => !isShipperOwned && handleDynamicComplianceChange(fieldKey, e.target.value)}
                                readOnly={isShipperOwned || (field.has_exempt_option && exemptions[fieldKey])}
                                placeholder={isShipperOwned ? '' : field.field_label}
                                style={(isShipperOwned || (field.has_exempt_option && exemptions[fieldKey])) ? {backgroundColor: 'var(--bg-disabled)'} : {}} />
                            {field.has_exempt_option && !isShipperOwned && (
                                <div className="exempt-checkbox-group">
                                    <input type="checkbox" id={`exempt-${fieldKey.replace(/\s+/g, '-')}`} checked={exemptions[fieldKey] || false}
                                        onChange={(e) => handleExemptionChange(fieldKey, e.target.checked)} />
                                    <label htmlFor={`exempt-${fieldKey.replace(/\s+/g, '-')}`} className="exempt-label">Exempt</label>
                                </div>)}
                        </div>
                    </React.Fragment>);
                })}
                </div>
            </div>)}
            {internationalApiDetails.line_items_customs_info?.length > 0 && (
            <div className="form-section"><h5>Customs Information per Item</h5><div className="customs-items-table-container">
            <table className="customs-items-table"><thead><tr><th>SKU</th><th>Qty</th><th>Name</th><th>Customs Desc.</th><th>Tariff</th><th>COO</th></tr></thead><tbody>
            {internationalApiDetails.line_items_customs_info.map(item => (<tr key={item.original_order_line_item_id}><td>{item.sku}</td><td>{item.quantity}</td><td>{item.product_name}</td><td>{item.customs_description}</td><td>{item.harmonized_tariff_code}</td><td>{item.default_country_of_origin}</td></tr>))}
            </tbody></table></div></div>)}
        </section>)}


      <section className="supplier-mode-selection card" style={{marginTop: 'var(--spacing-lg)'}}>
        <h3>Order Fulfillment Mode</h3>
        <div className="form-grid">
            <label htmlFor="mainSupplierTrigger">Fulfillment Type:</label>
            <select
                id="fulfillmentStrategy"
                value={selectedFulfillmentStrategy}
                onChange={handleFulfillmentStrategyChange}
                disabled={disableFormFields}
                required
            >
                <option value="" disabled>
                    -- Select Fulfillment Strategy --
                </option>
                {suppliers && suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                <option value={G1_ONSITE_INTERNATIONAL_VALUE}>
                    * G1 Onsite Fulfillment *
                </option>
            </select>
        </div>
        <p className="info-text card-inset" style={{marginTop:'var(--spacing-sm)'}}>
            The "Shipper" for the international label will always be Global One Technology, regardless of the mode selected above.
        </p>
      </section>

      {isSupplierPOFlow && (
        <section className="purchase-info card">
            <h3>Create PO for {suppliers.find(s=>s.id === parseInt(selectedFulfillmentStrategy, 10))?.name}</h3>
            <div className="form-grid">
                <label htmlFor="singlePoNotes">PO Notes/Payment Instructions:</label>
                <textarea id="singlePoNotes" value={singleOrderPoNotes} onChange={(e) => setSingleOrderPoNotes(e.target.value)} rows="3" disabled={disableFormFields} />
            </div>
            <div className="purchase-items-grid">
                <h4>Items to Purchase for PO:</h4>
                <div className="item-header-row"><span>Purchase SKU</span><span>Description</span><span>Qty</span><span>Unit Cost</span></div>
                {purchaseItems.map((item, index) => (
                     <div key={`po-item-${item.original_order_line_item_id || index}`} className="item-row">
                        <div><label className="mobile-label">SKU:</label><input type="text" value={item.skuInputValue || ''} onChange={(e) => handlePurchaseItemChange(index, 'skuInputValue', e.target.value)} placeholder="SKU" required disabled={disableFormFields} title={item.original_sku ? `Original: ${item.original_sku}` : ''} className="sku-input" /></div>
                        <div><label className="mobile-label">Desc:</label><textarea value={item.description || ''} onChange={(e) => handlePurchaseItemChange(index, 'description', e.target.value)} placeholder="Desc" rows={2} disabled={disableFormFields} className="description-textarea" /></div>
                        <div className="qty-cost-row">
                            <div><label className="mobile-label">Qty:</label><input type="number" value={item.quantity || 1} onChange={(e) => handlePurchaseItemChange(index, 'quantity', e.target.value)} min="1" required disabled={disableFormFields} className="qty-input" /></div>
                            <div><label className="mobile-label">Cost:</label><input type="number" value={item.unit_cost || ''} onChange={(e) => handlePurchaseItemChange(index, 'unit_cost', e.target.value)} step="0.01" min="0" placeholder="0.00" required disabled={disableFormFields} className="price-input" /></div>
                        </div>
                    </div>
                ))}
            </div>
        </section>
      )}

      {isSupplierPOFlow && profitInfo.isCalculable && (
          <ProfitDisplay info={profitInfo} />
      )}

      <section className="card" style={{marginTop: 'var(--spacing-lg)'}}>
          <h4>Final International Shipment Details (Common to all modes)</h4>
          <div className="form-grid">
              <label htmlFor="shipmentDescription">Overall Shipment Description*:</label>
              <input type="text" id="shipmentDescription" value={descriptionOfGoods} onChange={(e) => setDescriptionOfGoods(e.target.value.substring(0,50))} placeholder="e.g., Computer Parts" required disabled={disableFormFields} maxLength={50}/>
              <label htmlFor="intlShipmentWeight">Total Shipment Weight (lbs)*:</label>
              <input type="number" id="intlShipmentWeight" placeholder="e.g., 10.5" step="0.1" min="0.1" value={shipmentWeight} onChange={(e) => setShipmentWeight(e.target.value)} required disabled={disableFormFields}/>
              <label htmlFor="intlPackageLength">Package Length (in):</label>
              <input type="number" id="intlPackageLength" value={packageLength} onChange={(e) => setPackageLength(e.target.value)} step="0.1" min="0.1" disabled={disableFormFields}/>
              <label htmlFor="intlPackageWidth">Package Width (in):</label>
              <input type="number" id="intlPackageWidth" value={packageWidth} onChange={(e) => setPackageWidth(e.target.value)} step="0.1" min="0.1" disabled={disableFormFields}/>
              <label htmlFor="intlPackageHeight">Package Height (in):</label>
              <input type="number" id="intlPackageHeight" value={packageHeight} onChange={(e) => setPackageHeight(e.target.value)} step="0.1" min="0.1" disabled={disableFormFields}/>
              <label htmlFor="intlShippingService">International Shipping Service*:</label>
              <select id="intlShippingService" value={selectedShippingService} onChange={(e) => setSelectedShippingService(e.target.value)} required disabled={disableFormFields}>
                  <option value="">-- Select Service --</option>
                  {SHIPPING_METHODS_OPTIONS_INTL.map(opt => ( <option key={opt.value} value={opt.value}>{opt.label}</option> ))}
              </select>

             <label htmlFor="billToCustomerUpsIntl">Bill Recipient UPS Account:</label>
             <input
                 type="checkbox"
                 id="billToCustomerUpsIntl"
                 checked={billToCustomerUps}
                 onChange={(e) => {
                     setBillToCustomerUps(e.target.checked);
                     if (e.target.checked) {
                         setCustomerUpsAccountNumber(order?.customer_ups_account_number || '');
                         const billingZip = billing_address?.zip || order?.customer_billing_zip;
                         setCustomerUpsAccountZipCode(billingZip ? String(billingZip).replace(/\s+/g, '') : '');
                     } else {
                         setCustomerUpsAccountNumber('');
                         setCustomerUpsAccountZipCode('');
                     }
                 }}
                 disabled={disableFormFields}
             />
             {billToCustomerUps && (
                 <>
                     <label htmlFor="customerUpsAccountIntl">Recipient UPS Acct #*:</label>
                     <input
                         type="text"
                         id="customerUpsAccountIntl"
                         value={customerUpsAccountNumber}
                         onChange={(e) => setCustomerUpsAccountNumber(e.target.value)}
                         placeholder="Recipient's UPS Account Number"
                         required
                         disabled={disableFormFields}
                     />
                     <label htmlFor="customerUpsAccZipIntl">Recipient Acct Postal Code*:</label>
                     <input
                         type="text"
                         id="customerUpsAccZipIntl"
                         value={customerUpsAccountZipCode}
                         onChange={(e) => setCustomerUpsAccountZipCode(e.target.value.replace(/\s+/g, ''))}
                         placeholder="Account Postal Code (no spaces)"
                         required
                         disabled={disableFormFields}
                     />
                 </>
             )}

              <label htmlFor="brandingOption">Packing Slip Branding:</label>
              <select id="brandingOption" value={isBlindDropShip ? 'blind' : 'g1'} onChange={handleBrandingChange} disabled={disableFormFields}>
                  <option value="g1">Global One Technology Branding</option>
                  <option value="blind">Blind Ship (Generic Packing Slip)</option>
              </select>
          </div>
      </section>

      <div className="order-actions" style={{ marginTop: 'var(--spacing-lg)'}}>
          {processSuccess ? (
              <div className="success-message-box">
                  <h4>Order Processed Successfully!</h4>
                  {newShipmentInfo.poNumber && <p><strong>PO Number:</strong> {newShipmentInfo.poNumber}</p>}
                  {newShipmentInfo.trackingNumber && <p><strong>Tracking Number:</strong> {newShipmentInfo.trackingNumber}</p>}
              </div>
          ) : (
              <button type="button" className="process-order-button" onClick={handleProcessCombinedOrder}
                  disabled={loadingApiDetails || isProcessingOrder || !internationalApiDetails || !shipmentWeight || !selectedShippingService || (billToCustomerUps && (!customerUpsAccountNumber || !customerUpsAccountZipCode)) || !selectedFulfillmentStrategy }>
                  {isProcessingOrder ? 'Processing...' : (isSupplierPOFlow ? 'Create PO & Generate Intl. Label' : 'Generate G1 Intl. Label')}
              </button>
          )}
      </div>
    </div>
  );
}

export default InternationalOrderProcessor;