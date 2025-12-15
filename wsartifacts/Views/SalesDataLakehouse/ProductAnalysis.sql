-- Product Analysis View
-- Analyzes product performance based on sales summary
CREATE VIEW dbo.ProductAnalysis
AS
SELECT 
    p.ProductID,
    p.ProductName,
    p.Category,
    ss.Region,
    SUM(ss.TotalQuantity) AS TotalUnitsSold,
    SUM(ss.TotalAmount) AS TotalRevenue,
    AVG(ss.AvgTransactionAmount) AS AvgOrderValue,
    COUNT(DISTINCT ss.SaleDate) AS DaysWithSales
FROM dbo.DimProduct p
INNER JOIN dbo.SalesSummary ss ON p.ProductID = ss.ProductID
GROUP BY p.ProductID, p.ProductName, p.Category, ss.Region;
