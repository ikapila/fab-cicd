-- Sales Summary View
-- Aggregates daily sales data by product and region
CREATE VIEW dbo.SalesSummary
AS
SELECT 
    ProductID,
    Region,
    SaleDate,
    SUM(Quantity) AS TotalQuantity,
    SUM(Amount) AS TotalAmount,
    COUNT(*) AS TransactionCount,
    AVG(Amount) AS AvgTransactionAmount
FROM dbo.FactSales
WHERE SaleDate >= DATEADD(YEAR, -2, GETDATE())
GROUP BY ProductID, Region, SaleDate;
