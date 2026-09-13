const {defineConfig,devices}=require('@playwright/test');
module.exports=defineConfig({
 testDir:'./tests',timeout:90000,expect:{timeout:30000},fullyParallel:false,workers:1,retries:0,
 reporter:[['list'],['html',{open:'never'}],['junit',{outputFile:'test-results/browser.xml'}]],
 use:{baseURL:'http://127.0.0.1:8790',trace:'retain-on-failure',screenshot:'only-on-failure'},
 webServer:{command:'python3 -m http.server 8790 --bind 127.0.0.1 --directory .',url:'http://127.0.0.1:8790',reuseExistingServer:false},
 projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},{name:'firefox',use:{...devices['Desktop Firefox']}},{name:'webkit',use:{...devices['Desktop Safari']}},{name:'mobile-chromium',use:{...devices['Pixel 7']}}]
});
