# download 'Winpython64-3.7.6.0.exe' installer
# run it and allow it to extract to your desktop
# this will put a 'WPy64-3760' folder on your desktop.
#
# also downloand and install NSIS 3.05 from https://nsis.sourceforge.io/Download
#
# In windows explorer browse into the Desktop/WPy64-3760/ folder then double-click the 'WinPython Command Prompt.exe' to open a special cmd.exe dos box.
#
# Assuming u started inside the above 'WinPython Command Prompt.exe' dos box before u run this .bat file...
# cd to the folder where the 'gui_tool' cloned from the git hub repo exists
# run this file  'make_exe3.bat'

# Note, first we uninstall a bunch of big/scary pip/python packages that we defineitely do not want to bundle in the .exe
#  this helps as sometimes the pyinstaller dependancies get carried away and  bundle too much.  it can't bundle if its not installed

pip install pyinstaller
pip install wheel

pip uninstall -y cx_freeze
pip uninstall -y numba
pip uninstall -y numexpr
pip uninstall -y zmq
pip uninstall -y scikit-learn
pip uninstall -y seaborn
pip uninstall -y scs
pip uninstall -y tables
pip uninstall -y wordcloud
pip uninstall -y pandas
pip uninstall -y mizani
pip uninstall -y keras-vis
pip uninstall -y keras
pip uninstall -y sphinx
pip uninstall -y tcl
pip uninstall -y statsmodels
pip uninstall -y scikit-optimize
pip uninstall -y quantecon
pip uninstall -y pygbm
pip uninstall -y pyflux
pip uninstall -y plotnine
pip uninstall -y pdvega
pip uninstall -y mlxtend
pip uninstall -y imbalanced-learn
pip uninstall -y datashader
pip uninstall -y dask-searchcv
pip uninstall -y cvxpy
pip uninstall -y astroml

pip install numpy

echo you may delete \build and \dist folders if u want .
del dist\
del build\

# - unless your folder is EXACTLY C:\Users\user\Desktop\WPy64-3760\gui_tool\ you will need to edit paths in 
# the 'uavcan_gui_tool.spec.good' file to match your username.

copy uavcan_gui_tool.spec.good uavcan_gui_tool.spec

#pyinstaller --log-level=DEBUG --clean --noconfirm -d all --onedir uavcan_gui_tool.spec 
pyinstaller --noconfirm --onedir -d all --clean uavcan_gui_tool.spec

# make installer from binaries with NSIS  - unless your folder 
# is EXACTLY C:\Users\user\Desktop\WPy64-3760\gui_tool\ you will need to edit paths in 
# the .nsi file to match your username.
"C:\Program Files (x86)\NSIS\makensisw.exe" "UAVCAN GUI Tool2.nsi"
