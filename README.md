Go look at the original Audible activator and I'll explain what changed from it.  https://github.com/inAudible-NG/audible-activator

So the last Commit was 5 years ago, 5 years ago Selenium used different Syntax than Modern Version 4 does and it's been altered in a way
that wasn't backwards compatible with it's former versions and the syntax Python required

Suggested usage especially if like me you have 2FA enabled which if you take security seriously you ought to.

./audible-activator-with-manual-login.py -d 

also pip install --user requests  # use "easy_install" if pip is missing

pip install --user selenium

Download and extract the correct ChromeDriver zip file from here to this folder.

Download Google Chrome from https://www.google.com/chrome/ and install it on your computer.

so in essencce this one has been updated to the latest Selenium so that it works without needing to use old versions of Selenium.




